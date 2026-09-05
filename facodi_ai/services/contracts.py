from collections import Counter

from pydantic import BaseModel, Field

from .errors import ValidationError


class TranslationInputUnit(BaseModel):
    id: str
    source_sha: str
    text: str
    protected_tokens: list[str] = Field(default_factory=list)


class TranslationUnitResult(BaseModel):
    id: str
    translated_text: str


class TranslationResult(BaseModel):
    units: list[TranslationUnitResult]


def validate_translation_result(request_units, result):
    request_ids = [unit.id for unit in request_units]
    result_ids = [unit.id for unit in result.units]
    if len(request_ids) != len(set(request_ids)):
        raise ValidationError("Translation request contains duplicate unit IDs.")
    if len(result_ids) != len(set(result_ids)):
        raise ValidationError("Translation result contains duplicate unit IDs.")
    if len(request_ids) != len(result_ids) or set(request_ids) != set(result_ids):
        raise ValidationError("Translation result IDs do not match the request.")

    result_by_id = {unit.id: unit for unit in result.units}
    for request_unit in request_units:
        translated_text = result_by_id[request_unit.id].translated_text
        expected = Counter(request_unit.protected_tokens)
        for token, count in expected.items():
            if translated_text.count(token) != count:
                raise ValidationError(
                    f"Protected tokens were not preserved for unit '{request_unit.id}'."
                )
    return result
