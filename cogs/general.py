# cogs/general.py
import discord
from discord.ext import commands
import datetime
import database as db
from .utils import checks
from discord import app_commands

# --- VIEW MỚI CHO LỆNH HELP ---


class HelpView(discord.ui.View):
    def __init__(self, bot, author):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.author = author

        # Tạo các lựa chọn cho menu thả xuống từ các cogs của bot
        options = [
            discord.SelectOption(
                label=cog_name,
                description=cog.description,
                # Sửa lỗi chính tả từ COG_EMOJI
                emoji=getattr(cog, "COG_EMOJI", None)
            )
            for cog_name, cog in bot.cogs.items()
            # Chỉ hiển thị các cogs có emoji (cogs chính)
            if hasattr(cog, "COG_EMOJI")
        ]

        # Thêm lựa chọn "Trang chính" vào đầu danh sách
        options.insert(0, discord.SelectOption(
            label="Trang Chính",
            description="Quay về trang giới thiệu ban đầu.",
            emoji="🏠"
        ))

        self.select_menu = discord.ui.Select(
            placeholder="Chọn một danh mục để xem...",
            options=options
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Đây không phải bảng trợ giúp của bạn!", ephemeral=True)
            return False
        return True

    async def create_main_embed(self) -> discord.Embed:
        """Tạo embed cho trang chính."""
        embed = discord.Embed(
            title="✨ Bảng Trợ Giúp Của Bot ✨",
            description=f"Bot này hỗ trợ cả **Slash Commands** (`/`) và **Prefix Commands** (`{self.bot.command_prefix}`).\n"
            f"Sử dụng menu bên dưới để khám phá các nhóm lệnh khác nhau.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        # Đếm tổng số lệnh
        total_commands = len(self.bot.commands)
        embed.add_field(
            name="Tổng quan",
            value=f"Hiện có **{len(self.bot.cogs)}** nhóm lệnh với tổng cộng **{total_commands}** lệnh có sẵn.",
            inline=False
        )
        embed.set_footer(
            text=f"Yêu cầu bởi {self.author.display_name}", icon_url=self.author.display_avatar.url)
        return embed

    async def select_callback(self, interaction: discord.Interaction):
        """Callback khi người dùng chọn một mục trong menu."""
        selected_cog_name = self.select_menu.values[0]

        if selected_cog_name == "Trang Chính":
            await interaction.response.edit_message(embed=await self.create_main_embed())
            return

        cog = self.bot.get_cog(selected_cog_name)
        if not cog:
            await interaction.response.send_message("Lỗi: Không tìm thấy danh mục này.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{getattr(cog, 'COG_EMOJI', '❓')} Danh mục: {selected_cog_name}",
            description=cog.description,
            color=discord.Color.random()
        )

        commands_list = []
        for command in cog.get_commands():
            # Chỉ hiển thị các lệnh hybrid và không ẩn
            if isinstance(command, (commands.HybridCommand, commands.HybridGroup)) and not command.hidden:
                # Tạo chuỗi tham số cho mô tả
                params = " ".join(
                    [f"<{name}>" for name in command.clean_params])
                commands_list.append(
                    f"**`/{command.name} {params}`**\n*Lệnh con:* `?{command.name}`\n{command.description or 'Chưa có mô tả.'}")

        if commands_list:
            embed.add_field(name="Các lệnh có sẵn",
                            value="\n\n".join(commands_list), inline=False)
        else:
            embed.description += "\n\n*Không có lệnh nào trong danh mục này.*"

        embed.set_footer(
            text=f"Yêu cầu bởi {self.author.display_name}", icon_url=self.author.display_avatar.url)

        await interaction.response.edit_message(embed=embed)


# --- COG CHÍNH ---
class General(commands.Cog):
    """🌐 Các lệnh chung và sự kiện thành viên."""
    COG_EMOJI = "🌐"

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        config = await db.get_or_create_config(member.guild.id)
        if (channel_id := config.get('welcome_channel_id')) and (channel := self.bot.get_channel(channel_id)):
            embed = discord.Embed(title=f"Chào mừng đến với {member.guild.name}!", description=f"Xin chào {member.mention}, chúc bạn có những giây phút vui vẻ!", color=discord.Color.green(
            ), timestamp=datetime.datetime.now(datetime.timezone.utc))
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)
        if level_cog := self.bot.get_cog('LevelSystem'):
            await level_cog.update_level_role(member, 1)

        if (main_chat_id := config.get('main_chat_channel_id')) and (main_chat_channel := self.bot.get_channel(main_chat_id)):
            try:
                # Tạo một embed đơn giản, thân thiện
                chat_embed = discord.Embed(
                    description=f"Cả nhà ơi, cùng chào đón thành viên mới **{member.display_name}** đã gia nhập ngôi nhà chung của chúng ta nào! 🎉",
                    color=discord.Color.random()
                )

                # Gửi tin nhắn ping @everyone và @thành_viên_mới
                await main_chat_channel.send(
                    content=f"@everyone Chào mừng {member.mention}!",
                    embed=chat_embed,
                    # Đảm bảo bot có quyền ping
                    allowed_mentions=discord.AllowedMentions(
                        everyone=True, users=True)
                )
            except discord.Forbidden:
                print(
                    f"Lỗi: Bot không có quyền gửi tin nhắn hoặc ping @everyone trong kênh chat chính của server {member.guild.name}")
            except Exception as e:
                print(
                    f"Lỗi không xác định khi gửi thông báo chào mừng ở kênh chat: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        config = await db.get_or_create_config(member.guild.id)
        if (channel_id := config.get('goodbye_channel_id')) and (channel := self.bot.get_channel(channel_id)):
            embed = discord.Embed(title="👋 Tạm biệt", description=f"**{member.display_name}** đã rời khỏi server.",
                                  color=discord.Color.dark_grey(), timestamp=datetime.datetime.now(datetime.timezone.utc))
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(
                text=f"Hiện tại server có {member.guild.member_count} thành viên.")
            await channel.send(embed=embed)

    @commands.hybrid_command(name="help", description="Hiển thị bảng trợ giúp tương tác của bot.")
    async def custom_help(self, ctx: commands.Context):
        """Lệnh help tương tác với menu thả xuống."""
        view = HelpView(self.bot, ctx.author)
        initial_embed = await view.create_main_embed()
        # Gửi riêng tư
        await ctx.send(embed=initial_embed, view=view, ephemeral=True)

    @commands.hybrid_command(name='avatar', description="Xem ảnh đại diện của bạn hoặc người khác.")
    @app_commands.rename(member="thành_viên")
    async def avatar(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(
            title=f"Avatar của {member.display_name}", color=member.color)
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='members', description="Đếm số lượng thành viên trong server.")
    async def members(self, ctx: commands.Context):
        guild = ctx.guild
        total_members, bot_count = guild.member_count, sum(
            1 for member in guild.members if member.bot)
        user_count = total_members - bot_count
        online_users = sum(
            1 for m in guild.members if not m.bot and m.status == discord.Status.online)
        idle_users = sum(
            1 for m in guild.members if not m.bot and m.status == discord.Status.idle)
        dnd_users = sum(
            1 for m in guild.members if not m.bot and m.status == discord.Status.dnd)
        embed = discord.Embed(title=f"Thống kê Thành viên tại {guild.name}", color=discord.Color.blue(
        ), timestamp=datetime.datetime.now(datetime.timezone.utc))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(
            name="📊 Tổng quan", value=f"**👥 Tổng cộng:** `{total_members}`\n**👤 Người dùng:** `{user_count}`\n**🤖 Bot:** `{bot_count}`", inline=True)
        embed.add_field(
            name="📈 Trạng thái", value=f"**🟢 Online:** `{online_users}`\n**🟡 Idle:** `{idle_users}`\n**🔴 DND:** `{dnd_users}`", inline=True)
        embed.set_footer(
            text=f"Yêu cầu bởi {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='serverinfo', description="Xem thông tin chi tiết về server.")
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild
        embed = discord.Embed(title=f"Thông tin Server: {guild.name}", color=guild.owner.color if guild.owner else discord.Color.blue(
        ), timestamp=datetime.datetime.now(datetime.timezone.utc))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)
        ts = int(guild.created_at.timestamp())
        embed.add_field(name="🌐 Thông Tin Chung",
                        value=f"**👑 Chủ sở hữu:** {guild.owner.mention}\n**🆔 ID:** `{guild.id}`\n**🗓️ Ngày tạo:** <t:{ts}:F> (<t:{ts}:R>)", inline=False)
        total, online, bots = guild.member_count, sum(
            1 for m in guild.members if m.status != discord.Status.offline), sum(1 for m in guild.members if m.bot)
        embed.add_field(name="👨‍👩‍👧‍👦 Thành Viên",
                        value=f"**👥 Tổng:** `{total}` | **🟢 Online:** `{online}`\n**👤 Người dùng:** `{total - bots}` | **🤖 Bot:** `{bots}`", inline=True)
        embed.add_field(
            name="📺 Kênh", value=f"**🗨️ Text:** `{len(guild.text_channels)}`\n**🔊 Voice:** `{len(guild.voice_channels)}`", inline=True)
        embed.add_field(
            name="✨ Khác", value=f"**💎 Boost:** `Cấp {guild.premium_tier}` ({guild.premium_subscription_count} lượt)\n**🏷️ Roles:** `{len(guild.roles)}`", inline=False)
        embed.set_footer(
            text=f"Yêu cầu bởi {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(General(bot))
