from PIL import Image

from imgutils.operate import ImageBasedCensor, register_censor_method
from imgutils.operate import censor_areas
from plot import image_plot

if __name__ == '__main__':
    register_censor_method('star', ImageBasedCensor, images=['star.png'])

    image = Image.open('genshin_post.jpg')
    censor_img = Image.open('star.png')
    areas = [
        (967, 143, 1084, 261),
        (246, 208, 331, 287),
        (662, 466, 705, 514),
        (479, 283, 523, 326)
    ]

    image_plot(
        (image, 'origin'),
        (censor_img, 'star.png'),
        (censor_areas(image, 'star', areas), 'censored'),
        columns=2,
        figsize=(8, 6),
    )
