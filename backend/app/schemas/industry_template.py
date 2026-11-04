from pydantic import BaseModel, ConfigDict, Field, field_validator


class TemplateContent(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default='', max_length=500)
    positioning: str = Field(min_length=1, max_length=2000)
    themes: list[str] = Field(default_factory=list, max_length=30)
    material_hints: list[str] = Field(default_factory=list, max_length=30)
    terminology: list[str] = Field(default_factory=list, max_length=50)
    forbidden_expressions: list[str] = Field(default_factory=list, max_length=30)
    selection_keywords: list[str] = Field(default_factory=list, max_length=50)
    publish_tone: str = Field(default='自然、具体，避免空泛宣传', max_length=1000)
    copy_guidance: str = Field(default='围绕成片真实呈现的亮点展开', max_length=2000)

    @field_validator('themes', 'material_hints', 'terminology', 'forbidden_expressions', 'selection_keywords')
    @classmethod
    def clean_lines(cls, values):
        values = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v) > 500 for v in values):
            raise ValueError('每条规则最多500字')
        return values


class IndustryCreate(BaseModel):
    code: str = Field(pattern=r'^[a-z][a-z0-9_]{1,63}$')
    content: TemplateContent


class DraftUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    content: TemplateContent


class PublishTemplate(BaseModel):
    expected_revision: int = Field(ge=1)


class TemplateStatus(PublishTemplate):
    enabled: bool


