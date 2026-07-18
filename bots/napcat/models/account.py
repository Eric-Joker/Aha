from models.api import Stranger as AhaStranger


class Stranger(AhaStranger):
    uid: str
    qid: str
    is_years_vip: bool
    vip_level: int
    status: int
    login_days: int
