from math import ceil

import torch
from einops import rearrange
from einops.layers.torch import Rearrange
from torch import nn, einsum


# helpers

def exists(val):
    return val is not None


def default(val, d):
    return val if exists(val) else d


def cast_tuple(val, l=3):
    val = val if isinstance(val, tuple) else (val,)
    return (*val, *((val[-1],) * max(l - len(val), 0)))


def always(val):
    return lambda *args, **kwargs: val


# classes

class FeedForward(nn.Module):
    def __init__(self, dim, mult, dropout=0.):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(dim, dim * mult, 1),
            nn.Hardswish(),
            nn.Dropout(dropout),
            nn.Conv1d(dim * mult, dim, 1),
            nn.Dropout(dropout)
        )

    def forward(self, x):
        return self.net(x)


class Attention(nn.Module):
    def __init__(self, dim, fmap_size, heads=8, dim_key=32, dim_value=64, dropout=0., dim_out=None, downsample=False):
        super().__init__()
        inner_dim_key = dim_key * heads
        inner_dim_value = dim_value * heads
        dim_out = default(dim_out, dim)

        self.heads = heads
        self.scale = dim_key ** -0.5

        self.to_q = nn.Sequential(nn.Conv1d(dim, inner_dim_key, 1, stride=(2 if downsample else 1), bias=False),
                                  nn.BatchNorm1d(inner_dim_key))
        self.to_k = nn.Sequential(nn.Conv1d(dim, inner_dim_key, 1, bias=False), nn.BatchNorm1d(inner_dim_key))
        self.to_v = nn.Sequential(nn.Conv1d(dim, inner_dim_value, 1, bias=False), nn.BatchNorm1d(inner_dim_value))

        self.attend = nn.Softmax(dim=-1)
        self.dropout = nn.Dropout(dropout)

        out_batch_norm = nn.BatchNorm1d(dim_out)
        nn.init.zeros_(out_batch_norm.weight)

        self.to_out = nn.Sequential(
            nn.GELU(),
            nn.Conv1d(inner_dim_value, dim_out, 1),
            out_batch_norm,
            nn.Dropout(dropout)
        )

        # positional bias

        self.pos_bias = nn.Embedding(fmap_size, heads)

        q_pos = torch.arange(0, fmap_size, step=(2 if downsample else 1))
        k_pos = torch.arange(fmap_size)

        rel_pos = (q_pos[:, None, ...] - k_pos[None, :, ...]).abs()

        self.register_buffer('pos_indices', rel_pos)

    def apply_pos_bias(self, fmap):
        bias = self.pos_bias(self.pos_indices)
        bias = rearrange(bias, 'i j h -> () h i j')
        return fmap + (bias / self.scale)

    def forward(self, x):
        b, n, *_, h = *x.shape, self.heads

        q = self.to_q(x)
        l = q.shape[2]

        qkv = (q, self.to_k(x), self.to_v(x))
        q, k, v = map(lambda t: rearrange(t, 'b (h d) ... -> b h (...) d', h=h), qkv)

        dots = einsum('b h i d, b h j d -> b h i j', q, k) * self.scale

        dots = self.apply_pos_bias(dots)

        attn = self.attend(dots)
        attn = self.dropout(attn)

        out = einsum('b h i j, b h j d -> b h i d', attn, v)
        out = rearrange(out, 'b h l d -> b (h d) l', h=h, l=l)
        return self.to_out(out)


class Transformer(nn.Module):
    def __init__(self, dim, fmap_size, depth, heads, dim_key, dim_value, mlp_mult=2, dropout=0., dim_out=None,
                 downsample=False):
        super().__init__()
        dim_out = default(dim_out, dim)
        self.layers = nn.ModuleList([])
        self.attn_residual = (not downsample) and dim == dim_out

        for _ in range(depth):
            self.layers.append(nn.ModuleList([
                Attention(dim, fmap_size=fmap_size, heads=heads, dim_key=dim_key, dim_value=dim_value, dropout=dropout,
                          downsample=downsample, dim_out=dim_out),
                FeedForward(dim_out, mlp_mult, dropout=dropout)
            ]))

    def forward(self, x):
        for attn, ff in self.layers:
            attn_res = (x if self.attn_residual else 0)
            x = attn(x) + attn_res
            x = ff(x) + x
        return x


class LeSigTransformer(nn.Module):
    __model_name__ = 'le_transformer'

    def __init__(
            self,
            seq_len=180,
            num_classes=2,
            dim=(256, 384, 512),
            depth=4,
            heads=(4, 6, 8),
            mlp_mult=4,
            stages=3,
            dim_key=32,
            dim_value=64,
            dropout=0.1,
            num_distill_classes=None
    ):
        super().__init__()

        dims = cast_tuple(dim, stages)
        depths = cast_tuple(depth, stages)
        layer_heads = cast_tuple(heads, stages)

        assert all(map(lambda t: len(t) == stages, (dims, depths,
                                                    layer_heads))), 'dimensions, depths, and heads must be a tuple that is less than the designated number of stages'

        self.conv_embedding = nn.Sequential(
            nn.Conv1d(3, 32, 3, stride=1, padding=1),
            nn.Conv1d(32, 128, 3, stride=1, padding=1),
            # nn.Conv1d(64, 128, 3, stride = 1, padding = 1),
            nn.Conv1d(128, dims[0], 3, stride=1, padding=1)
        )

        fmap_size = seq_len // (1)
        layers = []

        for ind, dim, depth, heads in zip(range(stages), dims, depths, layer_heads):
            is_last = ind == (stages - 1)
            layers.append(Transformer(dim, fmap_size, depth, heads, dim_key, dim_value, mlp_mult, dropout))

            if not is_last:
                next_dim = dims[ind + 1]
                layers.append(
                    Transformer(dim, fmap_size, 1, heads * 2, dim_key, dim_value, dim_out=next_dim, downsample=True))
                fmap_size = ceil(fmap_size / 2)

        self.backbone = nn.Sequential(*layers)

        self.pool = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            Rearrange('... () -> ...')
        )

        self.distill_head = nn.Linear(dim, num_distill_classes) if exists(num_distill_classes) else always(None)
        self.mlp_head = nn.Linear(dim, num_classes)

    def forward(self, img):
        x = self.conv_embedding(img)
        x = self.backbone(x)
        x = self.pool(x)

        out = self.mlp_head(x)
        distill = self.distill_head(x)

        if exists(distill):
            return out, distill

        return out


if __name__ == '__main__':
    from thop import profile

    transformer = LeSigTransformer()
    input_ = torch.randn(1, 3, 180)

    flops, params = profile(transformer, (input_,))
    print('FLOPs = ' + str(flops / 1000 ** 3) + 'G')
    print('Params = ' + str(params / 1000 ** 2) + 'M')
