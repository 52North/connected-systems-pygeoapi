import logging
from dataclasses import field
from typing import Self

from ..definitions import *

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Observation:
    datastream_id: str  # id of the associated datastream
    resultTime: DateTime
    result: bytes  # raw result data

    id: Optional[str] = None  # unique identifier
    sampling_feature_id: Optional[str] = None
    procedure_link: Optional[str] = None
    phenomenonTime: Optional[DateTime] = None
    parameters: Optional[str] = None


@dataclass(frozen=True)
class TimescaleDbConfig:
    hostname: str
    port: int
    user: str
    password: str = field(repr=False)
    dbname: str

    pool_min_size: int = 10
    pool_max_size: int = 10

    drop_tables: bool = False  # True if existing tables should be dropped
    password_censored: str = "***********"

    def connection_string(self) -> str:
        return f"postgres://{self.user}:{self.password}@{self.hostname}:{self.port}/{self.dbname}"


class SchemaParser:
    """

    """

    def decode(self, data: any) -> Observation:
        """
        Formats a schema-defined input to an observation
        """
        return None

    def encode(self, obs: Observation) -> any:
        """
        Formats an observation into the specified output format
        """
        return None


class ObservationQuery:
    """ TODO: refactor this to be nicer """

    def __init__(self):
        self.clauses = []
        self.parameters = []
        self.limit = 10
        self.offset = 0

    def with_id(self, ids: List[str]) -> Self:
        return self._in("uuid", ids)

    def with_datastream(self, id: str) -> Self:
        self.clauses.append(f"datastream_id=${len(self.clauses) + 1}")
        self.parameters.append(id)
        return self

    def with_limit(self, limit: int) -> Self:
        if limit < 100_000:
            self.limit = limit
        else:
            self.limit = 100_000
        return self

    def with_offset(self, offset: int) -> Self:
        if offset > 0:
            self.offset = offset
        return self

    def _in(self, key: str, values: List[str]) -> Self:
        self.clauses.append(f"{key}=any(${len(self.clauses) + 1})")
        self.parameters.append(values)
        return self

    def with_time(self, key: str, time: TimeInterval) -> Self:
        if time is None:
            return self

        if time[0] is not None:
            self.clauses.append(f"{key}>=${len(self.clauses) + 1}")
            self.parameters.append(time[0])
        if time[1] is not None:
            self.clauses.append(f"{key}<=${len(self.clauses) + 1}")
            self.parameters.append(time[1])
        return self

    def to_sql(self, with_paging: bool = True) -> str:
        stub = ""
        # omit statement if none set
        if len(self.clauses) > 0:
            # first clause
            stub = "WHERE "
            stub += " AND ".join(self.clauses)

        if with_paging:
            stub += f" LIMIT {self.limit}"
            if self.offset > 0:
                stub += f" OFFSET {self.offset}"

        LOGGER.debug(f"querying with filter: {stub}")
        return stub
