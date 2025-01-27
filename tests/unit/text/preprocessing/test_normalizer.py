import pytest
from medkit.core.text import ModifiedSpan, Span
from medkit.core.text import Segment
from medkit.text.preprocessing import (
    Normalizer,
    NormalizerRule,
    LIGATURE_RULES,
    DOT_RULES,
    SIGN_RULES,
    QUOTATION_RULES,
    FRACTION_RULES,
    SPACE_RULES,
)


def _get_segment_from_text(text):
    return Segment(
        label="raw_text",
        spans=[Span(0, len(text))],
        text=text,
    )


TEST_PARAMS_CONFIG = [
    (
        [NormalizerRule(r"n\s*°", "number")],
        "À l'aide d'une canule n ° 3,",
        "À l'aide d'une canule number 3,",
        [
            Span(start=0, end=22),
            ModifiedSpan(length=6, replaced_spans=[Span(start=22, end=25)]),
            Span(start=25, end=28),
        ],
    ),
    (
        LIGATURE_RULES,
        "Il a un frère atteint de diabète.",
        "Il a un frère atteint de diabète.",
        [Span(start=0, end=33)],
    ),
    (
        LIGATURE_RULES,
        "Il a une sœur atteinte de diabète.",
        "Il a une soeur atteinte de diabète.",
        [
            Span(start=0, end=10),
            ModifiedSpan(length=2, replaced_spans=[Span(start=10, end=11)]),
            Span(start=11, end=34),
        ],
    ),
    (
        QUOTATION_RULES,
        """L`hématocrite "30,9"  « et plaquettes» 380 000.""",
        """L'hématocrite "30,9"  " et plaquettes" 380 000.""",
        [
            Span(start=0, end=1),
            ModifiedSpan(length=1, replaced_spans=[Span(start=1, end=2)]),
            Span(start=2, end=22),
            ModifiedSpan(length=1, replaced_spans=[Span(start=22, end=23)]),
            Span(start=23, end=37),
            ModifiedSpan(length=1, replaced_spans=[Span(start=37, end=38)]),
            Span(start=38, end=47),
        ],
    ),
    (
        SPACE_RULES,
        "EXTRÉMITÉS\xa0: l`examen\u2004capillaire en    moins de 2\xa0secondes.",
        "EXTRÉMITÉS : l`examen capillaire en    moins de 2 secondes.",
        [
            Span(start=0, end=10),
            ModifiedSpan(length=1, replaced_spans=[Span(start=10, end=11)]),
            Span(start=11, end=21),
            ModifiedSpan(length=1, replaced_spans=[Span(start=21, end=22)]),
            Span(start=22, end=49),
            ModifiedSpan(length=1, replaced_spans=[Span(start=49, end=50)]),
            Span(start=50, end=59),
        ],
    ),
    (
        FRACTION_RULES,
        "hémoglobine ¼ + ½ + ↉",
        "hémoglobine 1/4 + 1/2 + 0/3",
        [
            Span(start=0, end=12),
            ModifiedSpan(length=3, replaced_spans=[Span(start=12, end=13)]),
            Span(start=13, end=16),
            ModifiedSpan(length=3, replaced_spans=[Span(start=16, end=17)]),
            Span(start=17, end=20),
            ModifiedSpan(length=3, replaced_spans=[Span(start=20, end=21)]),
        ],
    ),
    (
        [*SIGN_RULES, *DOT_RULES],
        "Change this chars : © ® ™ … and ⋯",
        "Change this chars :    ... and ...",
        [
            Span(start=0, end=20),
            Span(start=21, end=22),
            Span(start=23, end=24),
            Span(start=25, end=26),
            ModifiedSpan(length=3, replaced_spans=[Span(start=26, end=27)]),
            Span(start=27, end=32),
            ModifiedSpan(length=3, replaced_spans=[Span(start=32, end=33)]),
        ],
    ),
]


@pytest.mark.parametrize(
    "rules,text,expected_text,expected_spans",
    TEST_PARAMS_CONFIG,
    ids=[
        "custom_user_rule",
        "text_classic",
        "ligatures_rules",
        "quotation_marks",
        "space_rules",
        "fraction_rules",
        "special_chars",
    ],
)
def test_normalizer(rules, text, expected_text, expected_spans):
    segment = _get_segment_from_text(text)
    norm_segment = Normalizer(output_label="NORMALIZED_TEXT", rules=rules).run(
        [segment]
    )[0]

    # Verify modifications
    assert norm_segment.label == "NORMALIZED_TEXT"
    assert norm_segment.text == expected_text
    assert norm_segment.spans == expected_spans
