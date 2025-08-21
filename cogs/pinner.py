# cogs/pinner.py
import discord
from discord import app_commands
from discord.ext import commands
import database as db
import json
from .utils import checks
import asyncio
from typing import Optional


async def _pin_id_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    all_pins = await db.get_all_pinned_messages(interaction.guild.id)
    choices = []
    for pin in all_pins:
        content_snippet = (pin['message_content']
                           or "*[Tin nhắn có embed]*")[:70]
        choice_name = f"ID: {pin['pin_id']} - \"{content_snippet}...\""
        if current.lower() in str(pin['pin_id']):
            choices.append(app_commands.Choice(
                name=choice_name, value=pin['pin_id']))
    return choices[:25]


class PinContentModal(discord.ui.Modal, title="Tạo Tin Nhắn Ghim Mới"):
    content_input = discord.ui.TextInput(
        label="Nội dung tin nhắn", style=discord.TextStyle.paragraph,
        placeholder="Nhập thông báo, luật lệ, hoặc bất cứ điều gì bạn muốn ghim ở đây...",
        required=True, max_length=1800
    )

    def __init__(self, pinner_cog):
        super().__init__()
        self.pinner_cog = pinner_cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        noi_dung = self.content_input.value
        sent_message = await interaction.channel.send(content=noi_dung)
        pin_id = await db.add_pinned_message(
            guild_id=interaction.guild.id, channel_id=interaction.channel.id, author_id=interaction.user.id,
            content=noi_dung, embed=None, last_message_id=sent_message.id
        )
        await interaction.followup.send(f"✅ Đã ghim tin nhắn mới thành công! ID của ghim là: `{pin_id}`.", ephemeral=True)


class Pinner(commands.Cog):
    """📌 Ghim và tự động di chuyển tin nhắn quan trọng."""
    COG_EMOJI = "📌"

    def __init__(self, bot):
        self.bot = bot
        self.repinning_locks = set()

    @commands.Cog.listener()
    async def on_ready(self):
        print("Pinner Cog: Bắt đầu kiểm tra và đồng bộ các tin nhắn đã ghim...")
        await asyncio.sleep(5)
        for guild in self.bot.guilds:
            await self.resync_pins_for_guild(guild)
        print("Pinner Cog: Đồng bộ hoàn tất.")

    async def resync_pins_for_guild(self, guild: discord.Guild):
        all_pins = await db.get_all_pinned_messages(guild.id)
        if not all_pins:
            return
        for pin in all_pins:
            try:
                channel = guild.get_channel(pin['channel_id'])
                if not channel or not channel.last_message_id:
                    continue
                try:
                    last_message = await channel.fetch_message(channel.last_message_id)
                    if last_message and last_message.id != pin['last_message_id']:
                        await self.repin_message(channel, pin)
                except discord.NotFound:
                    await self.repin_message(channel, pin)
            except Exception as e:
                print(f"Lỗi khi đồng bộ ghim {pin['pin_id']}: {e}")

    async def repin_message(self, channel: discord.TextChannel, pin_data: dict):
        if channel.id in self.repinning_locks:
            return
        self.repinning_locks.add(channel.id)
        try:
            try:
                old_message = await channel.fetch_message(pin_data['last_message_id'])
                await old_message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            content = pin_data['message_content']
            embed = discord.Embed.from_dict(json.loads(
                pin_data['embed_data'])) if pin_data['embed_data'] else None
            new_message = await channel.send(content=content, embed=embed)
            await db.update_last_message_id(pin_data['pin_id'], new_message.id)
        finally:
            self.repinning_locks.remove(channel.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        pinned_messages = await db.get_pinned_messages_for_channel(message.channel.id)
        if not pinned_messages:
            return
        for pin in pinned_messages:
            await self.repin_message(message.channel, pin)

    @commands.hybrid_command(name="ghim", description="Ghim một tin nhắn mới hoặc một tin nhắn có sẵn.")
    @checks.has_permissions(manage_messages=True)
    @app_commands.rename(message_id="id_tin_nhắn")
    async def ghim(self, ctx: commands.Context, message_id: Optional[str] = None):
        if message_id:
            await ctx.defer(ephemeral=True)
            try:
                message_to_pin = await ctx.channel.fetch_message(int(message_id))
            except (discord.NotFound, ValueError):
                return await ctx.send("❌ Không tìm thấy tin nhắn với ID này trong kênh hiện tại.", ephemeral=True)
            content = message_to_pin.content
            embed = message_to_pin.embeds[0] if message_to_pin.embeds else None
            sent_message = await ctx.channel.send(content=content, embed=embed)
            pin_id = await db.add_pinned_message(
                guild_id=ctx.guild.id, channel_id=ctx.channel.id, author_id=ctx.author.id,
                content=content, embed=embed, last_message_id=sent_message.id
            )
            await ctx.send(f"✅ Đã ghim tin nhắn có sẵn thành công! ID của ghim là: `{pin_id}`.", ephemeral=True)
        else:
            # SỬA LỖI: Kiểm tra nếu là lệnh prefix thì báo lỗi
            if not ctx.interaction:
                return await ctx.send("Lệnh này chỉ có thể tạo ghim mới qua Slash Command. Vui lòng dùng `/ghim` và để trống mục message_id.", ephemeral=True, delete_after=10)
            await ctx.interaction.response.send_modal(PinContentModal(self))

    @commands.hybrid_command(name="boghim", description="Bỏ ghim một tin nhắn tự động.")
    @app_commands.autocomplete(pin_id=_pin_id_autocomplete)
    @checks.has_permissions(manage_messages=True)
    @app_commands.rename(pin_id="id_ghim")
    async def boghim(self, ctx: commands.Context, pin_id: int):
        await ctx.defer(ephemeral=True)
        try:
            pin_id = int(pin_id)
        except ValueError:
            return await ctx.send("Vui lòng nhập một ID Ghim hợp lệ (là một con số).", ephemeral=True)
        pin_data = await db.get_pinned_message(pin_id, ctx.guild.id)
        if not pin_data:
            return await ctx.send(f"❌ Không tìm thấy ghim nào với ID `{pin_id}`.", ephemeral=True)
        try:
            channel = self.bot.get_channel(pin_data['channel_id']) or await self.bot.fetch_channel(pin_data['channel_id'])
            message = await channel.fetch_message(pin_data['last_message_id'])
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        await db.remove_pinned_message(pin_id)
        await ctx.send(f"✅ Đã bỏ ghim thành công tin nhắn có ID `{pin_id}`.", ephemeral=True)

    @commands.hybrid_command(name="danhsachghim", description="Xem tất cả các tin nhắn đang được ghim tự động trên server.")
    @checks.has_permissions(manage_messages=True)
    async def danhsachghim(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        all_pins = await db.get_all_pinned_messages(ctx.guild.id)
        if not all_pins:
            return await ctx.send("Không có tin nhắn nào đang được ghim tự động trên server này.", ephemeral=True)
        embed = discord.Embed(
            title=f"📌 Danh Sách Tin Nhắn Ghim Tự Động tại {ctx.guild.name}", color=discord.Color.blue())
        description = ""
        for pin in all_pins:
            channel = ctx.guild.get_channel(pin['channel_id'])
            channel_mention = channel.mention if channel else f"`Kênh ID: {pin['channel_id']}`"
            content_snippet = (pin['message_content']
                               or "*[Tin nhắn có embed]*")[:80]
            description += f"**ID Ghim:** `{pin['pin_id']}` | **Kênh:** {channel_mention}\n> ```{content_snippet}...```\n\n"
        embed.description = description
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Pinner(bot))
