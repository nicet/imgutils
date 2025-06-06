import pytest

from imgutils.tagging import drop_overlap_tags


@pytest.mark.unittest
class TestTaggingOverlap:
    def test_drop_overlap_tags(self, complex_dict_tags):
        assert drop_overlap_tags(['1girl', 'solo', 'long_hair', 'very_long_hair', 'red_hair']) == \
               ['1girl', 'solo', 'very_long_hair', 'red_hair']

        assert drop_overlap_tags(complex_dict_tags) == pytest.approx({
            '1girl': 0.998362123966217, 'solo': 0.9912548065185547, 'looking_at_viewer': 0.9146994352340698,
            'blush': 0.8892400860786438, 'smile': 0.43393653631210327, 'bangs': 0.49712443351745605,
            'large_breasts': 0.5196534395217896, 'navel': 0.9653235077857971, 'hair_between_eyes': 0.5786703824996948,
            'very_long_hair': 0.8142435550689697, 'closed_mouth': 0.9369247555732727, 'nipples': 0.9660118222236633,
            'purple_eyes': 0.9676010012626648, 'collarbone': 0.588348925113678, 'red_hair': 0.9200156331062317,
            'sweat': 0.8690457344055176, 'horns': 0.9711267948150635, 'spread_legs': 0.9603149890899658,
            'armpits': 0.9024748802185059, 'stomach': 0.6723923087120056, 'arms_up': 0.9380699396133423,
            'completely_nude': 0.9002960920333862, 'uncensored': 0.8612104058265686, 'pussy_juice': 0.6021570563316345,
            'feet_out_of_frame': 0.39779460430145264, 'on_bed': 0.610720157623291,
            'arms_behind_head': 0.44814401865005493, 'breasts_apart': 0.39798974990844727,
            'clitoris': 0.5310801267623901
        })

    def test_drop_overlap_tags_invalid(self):
        with pytest.raises(TypeError):
            drop_overlap_tags(1)
        with pytest.raises(TypeError):
            drop_overlap_tags(None)
