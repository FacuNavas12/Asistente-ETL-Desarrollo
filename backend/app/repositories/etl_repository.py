from app.models.etl import Etl
from app.repositories.base import BaseRepository

etl_repo: BaseRepository[Etl] = BaseRepository(Etl)
