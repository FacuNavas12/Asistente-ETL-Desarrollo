from app.models.job import Job
from app.repositories.base import BaseRepository

job_repo: BaseRepository[Job] = BaseRepository(Job)
