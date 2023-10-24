from pydantic import BaseModel
from typing import List


class Widget(BaseModel):
    name: str
    priority: int
    attributes: dict


class Section(BaseModel):
    name: str
    widgets: List[Widget]


class Structure(BaseModel):
    name: str
    sections: List[Section]
    config: dict