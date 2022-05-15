import asyncio
import asyncpg

class Database:
    def __init__(self):
        self.username = "user"
        self.password = "password"
        self.database = "gboozy"
        self.host = "0.0.0.0"
        self.connection: asyncpg.Connection = NotImplemented

    async def _initConn(self):
        self.connection = await asyncpg.connect(user=self.username, password=self.password,
                                     database=self.database, host=self.host)

    async def doQuery(self, query):
        await self.connection.execute(query)

    async def doFetch(self, query, args=""):
        return await self.connection.fetch(
            'SELECT * FROM mytable WHERE id = $1',
            10,
        )

loop = asyncio.get_event_loop()
loop.run_until_complete(run())