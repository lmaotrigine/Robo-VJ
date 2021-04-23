import base64
import math
import secrets


def bytes_to_int(x):
    return int.from_bytes(x, byteorder='big')


def int_to_bytes(n: int):
    num_bytes = int(math.ceil(n.bit_length() / 8))
    return n.to_bytes(num_bytes, byteorder='big')


class TokenUtils:
    def __init__(self, pool):
        self.pool = pool

    async def existing_token(self, user_id, app_id):
        query = 'SELECT app_name, secret FROM api_tokens WHERE user_id = $1, AND app_id = $2;'
        row = await self.pool.fetchrow(query, user_id, app_id)
        if not row:
            return None
        app_name, secret = row
        return app_name, self.encode_token(user_id, app_id, secret)

    async def new_token(self, user_id, app_name):
        secret = secrets.token_bytes()
        query = 'INSERT INTO api_tokens (user_id, app_name, secret) VALUES ($1, $2, $3) RETURNING app_id;'
        app_id = await self.pool.fetchval(query, user_id, app_name, secret)
        return self.encode_token(user_id, app_id, secret)

    async def regenerate_token(self, user_id, app_id):
        app_name = await self.delete_app(user_id, app_id)
        return await self.new_token(user_id, app_name)

    async def validate_token(self, token, user_id=None, app_id=None):
        try:
            token_user_id, token_app_id, secret = self.decode_token(token)
        except:
            secrets.compare_digest(token, token)
            return False

        if user_id is None:
            user_id = token_user_id
        if app_id is None:
            app_id = token_app_id

        query = 'SELECT secret FROM api_tokens WHERE user_id = $1 AND app_id = $2;'
        db_secret = await self.pool.fetchval(query, user_id, app_id)
        if db_secret is None:
            secrets.compare_digest(token, token)
            return False

        db_token = self.encode_token(user_id, app_id, db_secret)
        return (user_id, app_id) if secrets.compare_digest(token, db_token) else (None, None)

    async def delete_user_account(self, user_id):
        await self.pool.execute('DELETE FROM api_tokens WHERE user_id = $1;', user_id)

    async def delete_app(self, user_id, app_id):
        query = 'DELETE FROM api_tokens WHERE user_id = $1 AND app_id = $2 RETURNING app_name;'
        return await self.pool.fetchval(query, user_id, app_id)

    def generate_token(self, user_id, app_id):
        secret = base64.b64encode(secrets.token_bytes())
        return self.encode_token(user_id, app_id, secret)

    @classmethod
    def encode_token(cls, user_id, app_id, secret: bytes):
        user_id, app_id = map(int_to_bytes, (user_id, app_id))
        return b';'.join(map(base64.b64encode, (user_id, app_id, secret)))

    @classmethod
    def decode_token(cls, token):
        user_id, app_id, secret = map(base64.b64decode, token.split(b';'))
        user_id, app_id = map(bytes_to_int, (user_id, app_id))
        return user_id, app_id, secret
