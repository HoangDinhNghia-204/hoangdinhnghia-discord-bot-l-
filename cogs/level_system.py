# cogs/level_system.py
import discord
from discord.ext import commands
import random
import datetime
import database as db
import math
from .utils import checks
from discord import app_commands


class LeaderboardView(discord.ui.View):
    def __init__(self, author, guild, full_data, per_page=10):
        super().__init__(timeout=180.0)
        self.author = author
        self.guild = guild
        self.full_data = full_data
        self.per_page = per_page
        self.current_page = 0
        self.max_pages = math.ceil(len(self.full_data) / self.per_page)
        self.update_buttons()

    def create_embed(self) -> discord.Embed:
        start_index = self.current_page * self.per_page
        end_index = start_index + self.per_page
        page_data = self.full_data[start_index:end_index]

        embed = discord.Embed(
            title=f"🏆 Bảng Xếp Hạng tại {self.guild.name}", color=discord.Color.gold())
        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)

        lines = []
        medals = ['🥇', '🥈', '🥉']
        for i, user_data in enumerate(page_data):
            rank = start_index + i + 1
            member = self.guild.get_member(user_data['user_id'])
            if member:
                medal = medals[rank -
                               1] if rank <= 3 and self.current_page == 0 else f"**`{rank}.`**"
                top_role = f"| {member.top_role.mention}" if member.top_role.name != "@everyone" else ""
                line1 = f"{medal} {member.mention} {top_role}"

                xp, level, coins = user_data['xp'], user_data['level'], user_data['coins']
                xp_needed = 5 * (level ** 2) + 50 * level + 100

                fill_char = '🟩'
                empty_char = '⬛'
                bar_length = 5

                percent = (xp / xp_needed) if xp_needed > 0 else 0
                progress = int(percent * bar_length)
                progress_bar = f"`{fill_char * progress}{empty_char * (bar_length - progress)}`"

                line2 = f"> **Level {level}** • {progress_bar} ({int(xp):,}/{int(xp_needed):,} XP) • **{coins:,}** 💰"
                lines.append(f"{line1}\n{line2}")

        embed.description = "\n\n".join(lines)
        embed.set_footer(
            text=f"Trang {self.current_page + 1}/{self.max_pages}")
        return embed

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= self.max_pages - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Đây không phải bảng xếp hạng của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️ Trước", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Sau ➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class LevelSystem(commands.Cog):
    """⭐ Hệ thống Level, XP và Role thưởng"""
    COG_EMOJI = "⭐"

    def __init__(self, bot):
        self.bot = bot
        self.xp_multiplier = 1

    # cogs/level_system.py

    async def check_and_notify_achievements(self, channel: discord.TextChannel, member: discord.Member, unlocked_list: list):
        if not unlocked_list:
            return

        # Lấy kênh thông báo của server
        config = await db.get_or_create_config(member.guild.id)
        announcement_channel_id = config.get('announcement_channel_id')
        # Mặc định gửi ở kênh gốc nếu kênh thông báo chưa được set
        target_channel = self.bot.get_channel(
            announcement_channel_id) or channel

        for ach in unlocked_list:
            embed = discord.Embed(
                title="🏆 MỞ KHÓA THÀNH TỰU MỚI! 🏆",
                description=f"Xin chúc mừng **{member.mention}** đã đạt được một cột mốc đáng nhớ!",
                color=discord.Color.gold()
            )
            embed.add_field(
                name=f"{ach['badge_emoji']} {ach['name']}",
                value=f"*{ach['description']}*",
                inline=False
            )

            reward_parts = []
            if ach['reward_coin'] > 0:
                reward_parts.append(f"**{ach['reward_coin']:,}** 🪙")
            if ach['reward_xp'] > 0:
                reward_parts.append(f"**{ach['reward_xp']}** ⭐")

            if reward_parts:
                embed.add_field(
                    name="Phần Thưởng",
                    value=" + ".join(reward_parts),
                    inline=False
                )

            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(
                text="Hãy tiếp tục phấn đấu cho những thành tựu cao hơn!")

            try:
                await target_channel.send(embed=embed)
            except discord.Forbidden:
                # Nếu bot không có quyền gửi ở kênh thông báo, thử gửi ở kênh gốc
                if target_channel != channel:
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        pass  # Bỏ qua nếu cũng không có quyền ở kênh gốc

    async def update_level_role(self, member: discord.Member, new_level: int):
        if not member or not member.guild or member.bot:
            return

        server_level_roles = await db.get_level_roles(member.guild.id)
        if not server_level_roles:
            return

        target_role_id = None
        for level_milestone, role_id in sorted(server_level_roles.items(), key=lambda item: item[0], reverse=True):
            if new_level >= level_milestone:
                target_role_id = role_id
                break

        if not target_role_id:
            return

        target_role = member.guild.get_role(target_role_id)
        if not target_role:
            return

        roles_to_remove = [r for r in member.roles if r.id in server_level_roles.values(
        ) and r.id != target_role_id]

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Cập nhật role level")
            if target_role not in member.roles:
                await member.add_roles(target_role, reason=f"Đạt level {new_level}")
                embed = discord.Embed(title="✨ Đột Phá Cảnh Giới! ✨", description=f"Chúc mừng {member.mention} đã đạt đến cảnh giới mới và nhận được thân phận **{target_role.name}**!",
                                      color=target_role.color or discord.Color.random(), timestamp=datetime.datetime.now(datetime.timezone.utc))
                embed.set_thumbnail(url=member.display_avatar.url)

                config = await db.get_or_create_config(member.guild.id)
                if (channel_id := config.get('announcement_channel_id')) and (channel := self.bot.get_channel(channel_id)):
                    await channel.send(embed=embed)
        except discord.Forbidden:
            print(
                f"Bot không có quyền quản lý role trên server {member.guild.name}.")
        except Exception as e:
            print(f"Lỗi khi cập nhật role: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or message.content.startswith(self.bot.command_prefix):
            return

        config = await db.get_or_create_config(message.guild.id)
        if message.channel.id == config.get('command_channel_id'):
            return

        user_data = await db.get_or_create_user(message.author.id, message.guild.id)

        luck_role_id = config.get('luck_role_id')
        vip_role_id = config.get('vip_role_id')
        author_roles = message.author.roles
        xp_multiplier = 1.0
        coin_range = (1, 5)
        has_bonus_chance = False

        if luck_role_id and message.guild.get_role(luck_role_id) in author_roles:
            xp_multiplier, coin_range, has_bonus_chance = 1.25, (3, 8), True
        elif vip_role_id and message.guild.get_role(vip_role_id) in author_roles:
            xp_multiplier, coin_range = 1.10, (2, 6)
        if await db.get_user_active_effect(message.author.id, message.guild.id, 'xp_booster'):
            xp_multiplier *= 1.5  # Nhân thêm 50% (1.5 lần)
        coin_multiplier = 1.0
        if await db.get_user_active_effect(message.author.id, message.guild.id, 'coin_booster'):
            coin_multiplier = 1.25

        server_multiplier = float(self.xp_multiplier)
        xp_to_add = random.uniform(5, 15) * xp_multiplier * server_multiplier
        coins_to_add = random.randint(*coin_range) * coin_multiplier

        if has_bonus_chance and random.random() < 0.1:
            bonus_xp = random.uniform(20, 30) * server_multiplier
            bonus_coin = random.randint(10, 20) * coin_multiplier
            xp_to_add += bonus_xp
            coins_to_add += bonus_coin
            await message.channel.send(f"✨ Vận may mỉm cười! {message.author.mention} nhận thêm **{bonus_xp:.2f} XP** và **{bonus_coin} coin**!", delete_after=10)

        await db.update_user_xp(message.author.id, message.guild.id, xp_to_add)
        await db.update_coins(message.author.id, message.guild.id, int(coins_to_add))

        await db.update_quest_progress(message.author.id, message.guild.id, 'CHAT')
        unlocked_chat = await db.update_achievement_progress(message.author.id, message.guild.id, 'CHAT')
        await self.check_and_notify_achievements(message.channel, message.author, unlocked_chat)

        current_xp = user_data['xp'] + xp_to_add
        xp_needed = 5 * (user_data['level'] ** 2) + \
            50 * user_data['level'] + 100

        if current_xp >= xp_needed:
            new_level = user_data['level'] + 1
            await db.update_user_level(message.author.id, message.guild.id, new_level)
            level_up_coin = new_level * 100
            await db.update_coins(message.author.id, message.guild.id, level_up_coin)

            channel_to_send = self.bot.get_channel(config.get(
                'announcement_channel_id')) or message.channel
            await channel_to_send.send(f"🎉 Chúc mừng {message.author.mention} đã đạt **Level {new_level}** và nhận được **{level_up_coin}** coin!")

            unlocked_level = await db.update_achievement_progress(
                message.author.id, message.guild.id, 'REACH_LEVEL', value_to_add=new_level)
            await self.check_and_notify_achievements(channel_to_send, message.author, unlocked_level)

            await self.update_level_role(message.author, new_level)

    @commands.hybrid_command(name='level', description="Kiểm tra level và XP của bạn hoặc người khác.")
    @app_commands.rename(member="thành_viên")
    async def level(self, ctx: commands.Context, member: discord.Member = None):
        target_member = member or ctx.author
        user_data = await db.get_or_create_user(target_member.id, ctx.guild.id)

        level = user_data['level']
        xp = user_data['xp']
        xp_needed = 5 * (level**2) + 50 * level + 100

        fill, empty, bar_len = '🟩', '⬛', 10
        percent = (xp / xp_needed * 100) if xp_needed > 0 else 100
        progress = int(percent / 100 * bar_len)
        progress_bar = fill * progress + empty * (bar_len - progress)

        embed = discord.Embed(
            title=f"Thông tin Level của {target_member.display_name}", color=target_member.color)
        embed.set_thumbnail(url=target_member.display_avatar.url)
        embed.add_field(
            name="Cấp độ", value=f"**```{level}```**", inline=True)
        embed.add_field(
            name="Kinh nghiệm", value=f"**```{int(xp):,} / {int(xp_needed):,}```**", inline=True)
        embed.add_field(
            name=f"Tiến trình ({int(percent)}%)", value=progress_bar, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='leaderboard', aliases=['lb', 'top'], description="Xem bảng xếp hạng level của server.")
    async def leaderboard(self, ctx: commands.Context):
        full_lb_data = await db.get_leaderboard(ctx.guild.id, limit=100)
        if not full_lb_data:
            return await ctx.send("Chưa có ai trên bảng xếp hạng!", ephemeral=True)

        view = LeaderboardView(ctx.author, ctx.guild,
                               full_lb_data, per_page=10)
        initial_embed = view.create_embed()
        await ctx.send(embed=initial_embed, view=view)

    @commands.hybrid_group(name="leveladmin", description="Các lệnh quản lý hệ thống level (Admin).", hidden=True)
    async def leveladmin(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @leveladmin.command(name='addrole', description="Thêm một role thưởng khi đạt level nhất định.")
    @checks.has_permissions(manage_roles=True)
    @app_commands.rename(level="cấp_độ", role="role")
    async def addlevelrole(self, ctx: commands.Context, level: int, role: discord.Role):
        if level <= 0:
            return await ctx.send("Level phải là số dương.", delete_after=10, ephemeral=True)
        if ctx.guild.me.top_role <= role:
            return await ctx.send(f"Bot không thể quản lý role `{role.name}` vì role của bot thấp hơn.", delete_after=15, ephemeral=True)

        await db.add_level_role(ctx.guild.id, level, role.id)
        await ctx.send(embed=discord.Embed(description=f"✅ Đã đặt: Đạt **Level {level}** nhận role {role.mention}.", color=discord.Color.green()), delete_after=15)

    @leveladmin.command(name='removerole', description="Xóa một role thưởng khỏi mốc level.")
    @checks.has_permissions(manage_roles=True)
    @app_commands.rename(level="cấp_độ")
    async def removelevelrole(self, ctx: commands.Context, level: int):
        if await db.remove_level_role(ctx.guild.id, level) > 0:
            await ctx.send(embed=discord.Embed(description=f"✅ Đã xóa cấu hình role cho **Level {level}**.", color=discord.Color.green()), delete_after=15)
        else:
            await ctx.send(embed=discord.Embed(description=f"ℹ️ Không có cấu hình role nào cho **Level {level}**.", color=discord.Color.yellow()), delete_after=15)

    @leveladmin.command(name='viewroles', description="Xem tất cả cấu hình role-level của server.")
    @checks.has_permissions(manage_roles=True)
    async def viewlevelroles(self, ctx: commands.Context):
        level_roles = await db.get_level_roles(ctx.guild.id)
        embed = discord.Embed(
            title=f"Hệ thống Role-Level của {ctx.guild.name}", color=discord.Color.blue())

        if not level_roles:
            embed.description = f"Chưa có cấu hình. Dùng `/leveladmin addrole <level> <role>`."
        else:
            sorted_roles = sorted(level_roles.items(),
                                  key=lambda item: item[0], reverse=True)
            desc = "\n".join(
                [f"**Level {lv}**: {ctx.guild.get_role(rid).mention if ctx.guild.get_role(rid) else f'`Role đã xóa (ID: {rid})`'}" for lv, rid in sorted_roles])
            embed.description = desc

        await ctx.send(embed=embed)

    @leveladmin.command(name='setmultiplier', description="Đặt hệ số nhân XP & Coin cho tin nhắn (Admin).")
    @checks.is_administrator()
    @app_commands.rename(multiplier="hệ_số_nhân")
    async def setxpmultiplier(self, ctx: commands.Context, multiplier: int):
        self.xp_multiplier = max(1, multiplier)
        await ctx.send(f"✅ Đã đặt hệ số nhân XP và Coin khi chat thành **x{self.xp_multiplier}**!", delete_after=10)


async def setup(bot):
    await bot.add_cog(LevelSystem(bot))
