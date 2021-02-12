from discord.ext import commands, menus
import discord
import hashlib
import sys
from typing import Optional
import zlib

from cryptography.hazmat.backends.openssl import backend as openssl_backend
from cryptography.hazmat.primitives import hashes as crypto_hashes
import pygost.gost28147
import pygost.gost28147_mac
import pygost.gost34112012
import pygost.gost341194
import pygost.gost3412

from .utils.crypto import (decode_caesar_cipher, encode_caesar_cipher, decode_morse_code, encode_morse_code, UnitOutputError)
from .utils.paginator import RoboPages, SimplePages

class CryptoPages(SimplePages):
    def __init__(self, entries, *, title, per_page=12):
        super().__init__(entries=entries, per_page=per_page)
        self.embed.title = title

class Cryptography(commands.Cog):
    """Crypto functions."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['decrypt'], invoke_without_command=True)
    async def decode(self, ctx):
        """Decode coded messages"""
        await ctx.send_help(ctx.command)

    @decode.group(name='caesar', aliases=['rot'], invoke_without_command=True)
    async def decode_caesar(self, ctx, key: int, *, message: str):
        """Decode Caesar cipher."""
        await ctx.send(embed=discord.Embed(title='Decode Caesar Cipher', colour=discord.Colour.blurple(), description=decode_caesar_cipher(message, key)))

    @decode_caesar.command(name='brute')
    async def decode_caesar_brute(self, ctx, message: str):
        """Brute force decode caesar cipher"""
        data = [decode_caesar_cipher(message, key) for key in range(1, 26)]
        pages = CryptoPages(entries=data, title='Decode Caesar Brute Force (Ordered by key from 1-25', per_page=1)
        try:
            await pages.start(ctx)
        except menus.MenuError as e:
            await ctx.send(e)

    @decode.group(name='gost', aliases=['гост'], invoke_without_command=True)
    async def decode_gost(self, ctx):
        """Russian Federation/Soviet Union GOST
        Межгосударственный стандарт
        From GOsudarstvennyy STandart
        (ГОсударственный СТандарт)
        """
        await ctx.send_help(ctx.command)

    @decode_gost.group(name='28147-89', aliases=['magma', 'магма'], invoke_without_command=True)
    async def decode_gost_28147_89(self, ctx):
        """GOST 28147-89 block cipher
        Also known as Магма (Magma)
        key length must be 32 (256-bit)
        """
        await ctx.send_help(ctx.command)

    @decode_gost_28147_89.command(name='cbc')
    async def decode_gost_28147_89_cbc(self, ctx, key: str, *, data: str):
        """Magma with CBC mode of operation."""
        try:
            await ctx.send(embed=discord.Embed(title='Decode GOST Magma (CBC)', colour=discord.Colour.blurple(), description=pygost.gost28147.cbc_decrypt(key.encode("UTF-8"), bytearray.fromhex(data)).decode("UTF-8")))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @decode_gost_28147_89.command(name='cfb')
    async def decode_gost_28147_89_cfb(self, ctx, key: str, *, data: str):
        """Magma with CFB mode of operation."""
        try:
            await ctx.send(embed=discord.Embed(title='Decode GOST Magma (CFB)', colour=discord.Colour.blurple(), description=pygost.gost28147.cfb_decrypt(key.encode("UTF-8"), bytearray.fromhex(data)).decode("UTF-8")))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @decode_gost_28147_89.command(name='cnt')
    async def decode_gost_28147_89_cnt(self, ctx, key: str, *, data: str):
        """Magma with CNT mode of operation."""
        try:
            await ctx.send(embed=discord.Embed(title='Decode GOST Magma (CNT)', colour=discord.Colour.blurple(), description=pygost.gost28147.cnt_decrypt(key.encode("UTF-8"), bytearray.fromhex(data)).decode("UTF-8")))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @decode_gost_28147_89.command(name='ecb')
    async def decode_gost_28147_89_ecb(self, ctx, key: str, *, data: str):
        """Magma with ECB mode of operation.
        Data block size must be 8 (64-bit)
        This means the data length must be a multiple of 8
        """
        try:
            await ctx.send(embed=discord.Embed(title='Decode GOST Magma (ECB)', colour=discord.Colour.blurple(), description=pygost.gost28147.ecb_decrypt(key.encode("UTF-8"), bytearray.fromhex(data)).decode("UTF-8")))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @decode_gost.command(name='34.12-2015', aliases=['kuznyechik', 'кузнечик'])
    async def decode_gost_34_12_2015(self, ctx, key: str, *, data: str):
        """GOST 34.12-2015 128-bit block cipher
        Also known as Кузнечик or Kuznyechik.
        Key length >= 32, data length >= 16
        """
        if len(key) < 32:
            return await ctx.send('Key length must be at least 32')
        if len(data) < 16:
            return await ctx.send('Data length must be at least 16')
        await ctx.send(embed=discord.Embed(title='Decode GOST Kuznyechik', colour=discord.Colour.blurple(), description=pygost.gost3412.GOST3412Kuznechik(key.encode("UTF-8")).decrypt(bytearray.fromhex(data)).decode("UTF-8")))

    @decode.command(name='morse')
    async def decode_morse(self, ctx, *, message: str):
        """Decodes morse code."""
        try:
            await ctx.send(embed=discord.Embed(title='Decode Morse Code', colour=discord.Colour.blurple(), description=decode_morse_code(message)))
        except UnitOutputError as e:
            await ctx.send(f'Error: {e}')

    @decode.command(name='qr')
    async def decode_qr(self, ctx, file_url: Optional[str]):
        """Decodes QR code
        Input a file or attach an image
        """
        if not file_url:
            if ctx.message.attachments:
                file_url = ctx.message.attachments[0].url
            else:
                return await ctx.send('Please input a file URL or attach an image.')
        
        url = 'https://api.qrserver.com/v1/read-qr-code/'
        params = {'fileurl': file_url}
        async with self.bot.session.get(url, params=params) as resp:
            if resp.status == 400:
                return await ctx.send('Unknown Error.')
            data = await resp.json()
        if data[0]['symbol'][0]['error']:
            return await ctx.send(f"Error: {data[0]['symbol'][0]['error']}")
        decoded = data[0]['symbol'][0]['data'].replace('QR-Code:', '')
        embed = discord.Embed(title='Decode QR code', colour=discord.Colour.blurple())
        embed.set_image(url=file_url)
        if len(decoded) > 2048:
            embed.description = f'{decoded[:2045]}...'
            embed.set_footer(text='Decoded message exceeded character limit.')
        else:
            embed.description = decoded
        await ctx.send(embed=embed)

    @decode.command(name='reverse')
    async def decode_reverse(self, ctx, *, message: str):
        """Reverses text."""
        await ctx.send(embed=discord.Embed(title='Decode Reversed Text', colour=discord.Colour.blurple(), description=message[::-1]))

    @commands.group(aliases=['encrypt'], invoke_without_command=True)
    async def encode(self, ctx):
        """Encode messages."""
        await ctx.send_help(ctx.command)

    @encode.command(name='adler32', aliases=['adler-32'])
    async def encode_adler32(self, ctx, *, message: str):
        """Compute Adler-32 checksum."""
        await ctx.send(embed=discord.Embed(title='Encode Adler-32 Checksum', colour=discord.Colour.blurple(), description=zlib.adler32(message.encode('UTF-8'))))

    @encode.command(name='blake2b')
    async def encode_blake2b(self, ctx, *, message: str):
        """64-byte digest BLAKE2b."""
        digest = crypto_hashes.Hash(crypto_hashes.BLAKE2b(64), backend=openssl_backend)
        digest.update(message.encode('UTF-8'))
        await ctx.send(embed=discord.Embed(title='Encode BLAKE2b', colour=discord.Colour.blurple(), description=str(digest.finalize())))

    @encode.command(name='blake2s')
    async def encode_blake2s(self, ctx, *, message: str):
        """32-byte digest BLAKE2s."""
        digest = crypto_hashes.Hash(crypto_hashes.BLAKE2s(32), backend=openssl_backend)
        digest.update(message.encode('UTF-8'))
        await ctx.send(embed=discord.Embed(title='Encode BLAKE2s', colour=discord.Colour.blurple(), description=str(digest.finalize())))

    @encode.command(name='caesar', aliases=['rot'])
    async def encode_caesar(self, ctx, key: int, *, message: str):
        """Encode a message using a Caesar cipher."""
        await ctx.send(embed=discord.Embed(title='Encode Caesar Cipher', colour=discord.Colour.blurple(), description=encode_caesar_cipher(message, key)))

    @encode.command(name='crc32', aliases=['crc-32'])
    async def encode_crc32(self, ctx, *, message: str):
        """Compute CRC-32 checksum."""
        await ctx.send(embed=discord.Embed(title='Encode CRC-32 Checksum', colour=discord.Colour.blurple(), description=zlib.crc32(message.encode('UTF-8'))))

    @encode.group(name='gost', aliases=['гост'], invoke_without_command=True)
    async def encode_gost(self, ctx):
        """Russian Federation/Soviet Union GOST
        Межгосударственный стандарт
        From GOsudarstvennyy STandart
        (ГОсударственный СТандарт)
        """
        await ctx.send_help(ctx.command)

    @encode_gost.group(name='28147-89', aliases=['magma', 'магма'], invoke_without_command=True)
    async def encode_gost_28147_89(self, ctx):
        """GOST 28147-89 block cipher
        Also known as Магма (Magma)
        key length must be 32 (256-bit)
        """
        await ctx.send_help(ctx.command)

    @encode_gost_28147_89.command(name='cbc')
    async def encode_gost_28147_89_cbc(self, ctx, key: str, *, data: str):
        """Magma with CBC mode of operation."""
        try:
            await ctx.send(embed=discord.Embed(title='Encode GOST Magma (CBC)', colour=discord.Colour.blurple(), description=pygost.gost28147.cbc_encrypt(key.encode("UTF-8"), data.encode('UTF-8')).hex()))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @encode_gost_28147_89.command(name='cfb')
    async def encode_gost_28147_89_cfb(self, ctx, key: str, *, data: str):
        """Magma with CFB mode of operation."""
        try:
            await ctx.send(embed=discord.Embed(title='Encode GOST Magma (CFB)', colour=discord.Colour.blurple(), description=pygost.gost28147.cfb_encrypt(key.encode("UTF-8"), data.encode('UTF-8')).hex()))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @encode_gost_28147_89.command(name='cnt')
    async def encode_gost_28147_89_cnt(self, ctx, key: str, *, data: str):
        """Magma with CNT mode of operation."""
        try:
            await ctx.send(embed=discord.Embed(title='Encode GOST Magma (CNT)', colour=discord.Colour.blurple(), description=pygost.gost28147.cnt_encrypt(key.encode("UTF-8"), data.encode('UTF-8')).hex()))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @encode_gost_28147_89.command(name='ecb')
    async def encode_gost_28147_89_ecb(self, ctx, key: str, *, data: str):
        """Magma with ECB mode of operation.
        Data block size must be 8 (64-bit)
        This means the data length must be a multiple of 8
        """
        try:
            await ctx.send(embed=discord.Embed(title='Encode GOST Magma (ECB)', colour=discord.Colour.blurple(), description=pygost.gost28147.ecb_encrypt(key.encode("UTF-8"), data.encode('UTF-8')).hex()))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @encode_gost_28147_89.command(name='mac')
    async def encode_gost_28147_89_mac(self, ctx, key: str, *, data: str):
        """Magma with MAC mode of operation."""
        try:
            mac = pygost.gost28147_mac.MAC(key=key.encode('UTF-8'))
            mac.update(data.encode('UTF-8'))
            await ctx.send(embed=discord.Embed(title='Encode GOST Magma (MAC)', colour=discord.Colour.blurple(), description=mac.hexdigest()))
        except ValueError as e:
            await ctx.send(f'Error: {e}')

    @encode_gost.group(name='34.11-2012', aliases=['стрибог', 'streebog'], invoke_without_command=True)
    async def encode_gost_34_11_2012(self, ctx):
        """GOST 34.11-2012 hash function.
        Also known as Стрибог or Streebog
        """
        await ctx.send_help(ctx.command)

    @encode_gost_34_11_2012.command(name='256')
    async def encode_gost_34_11_2012_256(self, ctx, *, data: str):
        """GOST 34.11-2012 256-bit has function.
        Also known as Streebog-256
        """
        await ctx.send(embed=discord.Embed(title='Encode GOST Streebog-256', colour=discord.Colour.blurple(), description=pygost.gost34112012.GOST34112012(data.encode('UTF-8'), digest_size=32).hexdigest()))

    @encode_gost_34_11_2012.command(name='512')
    async def encode_gost_34_11_2012_512(self, ctx, *, data: str):
        """GOST 34.11-2012 512-bit has function.
        Also known as Streebog-512
        """
        await ctx.send(embed=discord.Embed(title='Encode GOST Streebog-512', colour=discord.Colour.blurple(), description=pygost.gost34112012.GOST34112012(data.encode('UTF-8'), digest_size=64).hexdigest()))
    
    @encode_gost.command(name='34.11-94')
    async def encode_gost_34_11_94(self, ctx, *, data: str):
        """GOST 34.11-94 hash function."""
        await ctx.send(embed=discord.Embed(title='Encode GOST 34.11-94', colour=discord.Colour.blurple(), description=pygost.gost341194.GOST341194(data.encode('UTF-8')).hexdigest()))

    @encode_gost.command(name='34.12-2015', aliases=['kuznyechik', 'кузнечик'])
    async def encode_gost_34_12_2015(self, ctx, key: str, *, data: str):
        """GOST 34.12-2015 128-bit block cipher
        Also known as Кузнечик or Kuznyechik.
        Key length >= 32, data length >= 16
        """
        if len(key) < 32:
            return await ctx.send('Key length must be at least 32')
        if len(data) < 16:
            return await ctx.send('Data length must be at least 16')
        await ctx.send(embed=discord.Embed(title='Encode GOST Kuznyechik', colour=discord.Colour.blurple(), description=pygost.gost3412.GOST3412Kuznechik(key.encode("UTF-8")).encrypt(data.encode('UTF-8')).hex()))

    @encode.command(name='md4')
    async def encode_md4(self, ctx, *, message: str):
        """Generate MD4 hash."""
        md4_hash = hashlib.new('MD4')
        md4_hash.update(message.encode('UTF-8'))
        await ctx.send(embed=discord.Embed(title='Encode MD4', colour=discord.Colour.blurple(), description=md4_hash.hexdigest()))
       
    @encode.command(name='md5')
    async def encode_md5(self, ctx, *, message: str):
        """Generate MD5 hash."""
        await ctx.send(embed=discord.Embed(title='Encode MD5', colour=discord.Colour.blurple(), description=hashlib.md5(message.encode('UTF-8')).hexdigest()))

    @encode.command(name='morse')
    async def encode_morse(self, ctx, *, message: str):
        """Encode a message in Morse Code."""
        try:
            await ctx.send(embed=discord.Embed(title='Encode Morse Code', colour=discord.Colour.blurple(), description=encode_morse_code(message)))
        except UnitOutputError as e:
            await ctx.send(f'Error: {e}')

    @encode.command(name='qr')
    async def encode_qr(self, ctx, *, message: str):
        """Encode a message in a QR code."""
        url = f'https://api.qrserver.com/v1/create-qr-code/?data={message.replace(" ", "+")}'
        await ctx.send(embed=discord.Embed(title='Encode QR', colour=discord.Colour.blurple()).set_image(url=url))

    @encode.command(name='reverse')
    async def encode_reverse(self, ctx, *, message: str):
        """Reverses text."""
        await ctx.send(embed=discord.Embed(title='Encode Reversed Text', colour=discord.Colour.blurple(), description=message[::-1]))

    @encode.command(name='ripemd160', aliases=['ripemd-160'])
    async def encode_ripemd160(self, ctx, *, message: str):
        """Generate RIPEMD-160 hash."""
        h = hashlib.new('RIPEMD160')
        h.update(message.encode('UTF-8'))
        await ctx.send(embed=discord.Embed(title='Encode RIPEMD-160', colour=discord.Colour.blurple(), description=h.hexdigest()))

    @encode.command(name='sha1', aliases=['sha-1'])
    async def encode_sha1(self, ctx, *, message: str):
        """Generate SHA-1 hash."""
        await ctx.send(embed=discord.Embed(title='Encode SHA-1', colour=discord.Colour.blurple(), description=hashlib.sha1(message.encode('UTF-8')).hexdigest()))

    @encode.command(name='sha224', aliases=['sha-224'])
    async def encode_sha224(self, ctx, *, message: str):
        """Generate SHA-224 hash."""
        await ctx.send(embed=discord.Embed(title='Encode SHA-224', colour=discord.Colour.blurple(), description=hashlib.sha224(message.encode('UTF-8')).hexdigest()))
    
    @encode.command(name='sha256', aliases=['sha-256'])
    async def encode_sha256(self, ctx, *, message: str):
        """Generate SHA-256 hash."""
        await ctx.send(embed=discord.Embed(title='Encode SHA-256', colour=discord.Colour.blurple(), description=hashlib.sha256(message.encode('UTF-8')).hexdigest()))

    @encode.command(name='sha384', aliases=['sha-384'])
    async def encode_sha384(self, ctx, *, message: str):
        """Generate SHA-384 hash."""
        await ctx.send(embed=discord.Embed(title='Encode SHA-384', colour=discord.Colour.blurple(), description=hashlib.sha384(message.encode('UTF-8')).hexdigest()))

    @encode.command(name='sha512', aliases=['sha-512'])
    async def encode_sha512(self, ctx, *, message: str):
        """Generate SHA-512 hash."""
        await ctx.send(embed=discord.Embed(title='Encode SHA-512', colour=discord.Colour.blurple(), description=hashlib.sha512(message.encode('UTF-8')).hexdigest()))

    @encode.command(name='whirlpool')
    async def encode_whirlpool(self, ctx, *, message: str):
        """Generate WHIRPOOL hash."""
        h = hashlib.new('WHIRLPOOL')
        h.update(message.encode('UTF-8'))
        await ctx.send(embed=discord.Embed(title='Encode WHIRLPOOL', colour=discord.Colour.blurple(), description=h.hexdigest()))

def setup(bot):
    bot.add_cog(Cryptography(bot))
