from dataclasses import dataclass
from dataclasses_json import dataclass_json
from typing import List

@dataclass_json
@dataclass
class ProductRecord:
    code: str        # AKA plu
    name: str
    _uom_str: str    # AKA basiseinheit
    lst_price: float # AKA basispreis FIXME Never use float for price, use BigDecimal or similar
    _categ_list: List[str]
    input_mode: str = "DECIMAL"