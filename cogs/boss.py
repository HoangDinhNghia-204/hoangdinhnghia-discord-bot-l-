# cogs/boss.py
import discord
from discord.ext import commands
import datetime
import random
import database as db
import math
from .utils import checks
from discord import app_commands

try:
    from .economy import SHOP_ITEMS
except (ImportError, SystemError):
    from economy import SHOP_ITEMS

ATTACK_COOLDOWN_SECONDS = 10

# =============================================================
# VIEW VÀ NÚT BẤM (ĐÃ NÂNG CẤP)
# =============================================================


class BossAttackView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance

    @discord.ui.button(label="Tấn Công", style=discord.ButtonStyle.red, emoji="⚔️", custom_id="boss_attack_button", row=0)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_attack(interaction)

    @discord.ui.button(label="Kiểm Tra Trạng Thái", style=discord.ButtonStyle.secondary, emoji="⏱️", custom_id="boss_status_button", row=0)
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Kiểm tra xem boss còn tồn tại không
        boss_data = await db.get_boss(interaction.guild.id)
        if not boss_data:
            return await interaction.response.send_message("💪 Boss đã bị tiêu diệt!", ephemeral=True)

        # Lấy dữ liệu tấn công của người dùng
        attacker_data = await db.get_attacker(interaction.guild.id, interaction.user.id)

        if not attacker_data or not attacker_data['last_attack_timestamp']:
            # Nếu chưa từng tấn công, họ đã sẵn sàng
            return await interaction.response.send_message("✅ Bạn đã sẵn sàng để tấn công!", ephemeral=True)

        # Tính toán thời gian hồi chiêu
        last_attack_time = datetime.datetime.fromisoformat(
            attacker_data['last_attack_timestamp'])
        cooldown_end = last_attack_time + \
            datetime.timedelta(seconds=ATTACK_COOLDOWN_SECONDS)

        if datetime.datetime.now(datetime.timezone.utc) >= cooldown_end:
            # Nếu thời gian hồi chiêu đã kết thúc
            return await interaction.response.send_message("✅ Bạn đã sẵn sàng để tấn công!", ephemeral=True)
        else:
            # Nếu còn trong thời gian hồi chiêu, gửi timestamp động
            end_timestamp = int(cooldown_end.timestamp())
            return await interaction.response.send_message(
                f"⏳ Bạn có thể tấn công lại <t:{end_timestamp}:R>.",
                ephemeral=True
            )


class VictoryLeaderboardView(discord.ui.View):
    def __init__(self, original_embed: discord.Embed, all_lines: list, per_page=10):
        super().__init__(timeout=180.0)
        self.original_embed = original_embed
        self.all_lines = all_lines
        self.per_page = per_page
        self.current_page = 0
        self.max_pages = math.ceil(len(self.all_lines) / self.per_page)
        self.update_buttons()

    def create_page_content(self) -> str:
        start_index = self.current_page * self.per_page
        end_index = start_index + self.per_page
        page_lines = self.all_lines[start_index:end_index]
        return "\n".join(page_lines)

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= self.max_pages - 1

    async def update_embed(self, interaction: discord.Interaction):
        self.original_embed.set_field_at(
            1,
            name="💰─── BẢNG CHIẾN LỢI PHẨM ───💰",
            value=self.create_page_content()
        )
        self.original_embed.set_footer(
            text=f"Trang {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=self.original_embed, view=self)

    @discord.ui.button(label="⬅️ Trước", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await self.update_embed(interaction)

    @discord.ui.button(label="Sau ➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await self.update_embed(interaction)


# HÀM MỚI (ĐÃ NÂNG CẤP)
def create_boss_embed(guild, boss_data, attackers_data=None):
    name = boss_data['boss_name']
    hp = boss_data['current_hp']
    max_hp = boss_data['max_hp']

    percent = (hp / max_hp) if max_hp > 0 else 0
    bar_len = 15
    fill = '🟥'
    empty = '⬛'
    progress = int(percent * bar_len)
    hp_bar = f"`{fill * progress}{empty * (bar_len - progress)}`"

    embed = discord.Embed(
        title=f"🔥 WORLD BOSS XUẤT HIỆN 🔥",
        description=f"Một con **{name}** hùng mạnh đã xuất hiện! Hãy cùng nhau tiêu diệt nó!",
        color=discord.Color.dark_red()
    )

    total_damage_dealt = max_hp - hp
    embed.add_field(
        name="🩸 Máu",
        value=f"**{hp:,} / {max_hp:,}**\n{hp_bar} ({percent:.2%})\n*Tổng sát thương đã gây: {total_damage_dealt:,}*",
        inline=False
    )

    if attackers_data:
        leaderboard_lines = []
        medals = ['🥇', '🥈', '🥉']
        # Chỉ hiển thị top 5 để embed không quá dài
        for i, attacker in enumerate(attackers_data[:5]):
            member = guild.get_member(attacker['user_id'])
            if member:
                rank = medals[i] if i < 3 else f"`#{i+1}`"
                leaderboard_lines.append(
                    f"{rank} {member.mention}: **{attacker['total_damage']:,}** sát thương"
                )

        if leaderboard_lines:
            embed.add_field(
                name="⚔️ Bảng Sát Thương ⚔️",
                value="\n".join(leaderboard_lines),
                inline=False
            )

    embed.set_footer(text="Nhấn nút 'Tấn Công' bên dưới!")
    return embed


class Boss(commands.Cog):
    """👹 Hệ thống World Boss."""
    COG_EMOJI = "👹"

    def __init__(self, bot):
        self.bot = bot
        bot.add_view(BossAttackView(self))

    @commands.hybrid_group(name="boss", description="Các lệnh liên quan đến World Boss.")
    async def boss(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @boss.command(name="spawn", description="Triệu hồi một World Boss (Admin).")
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(name="tên_boss", health="lượng_máu")
    async def spawn(self, ctx: commands.Context, name: str, health: int):
        if await db.get_boss(ctx.guild.id):
            return await ctx.send("Đã có một World Boss đang hoạt động! Dùng `/boss despawn` để xóa.", ephemeral=True)
        if health <= 0:
            return await ctx.send("Máu của boss phải lớn hơn 0.", ephemeral=True)
        boss_data = {'boss_name': name, 'current_hp': health, 'max_hp': health}
        embed = create_boss_embed(ctx.guild, boss_data)
        view = BossAttackView(self)
        boss_msg = await ctx.send(embed=embed, view=view)
        await db.create_boss(ctx.guild.id, name, health, boss_msg.id, ctx.channel.id, ctx.author.id)

    @boss.command(name="despawn", description="Xóa World Boss hiện tại khỏi server (Admin).")
    @commands.has_permissions(manage_guild=True)
    async def despawn(self, ctx: commands.Context):
        boss_data = await db.get_boss(ctx.guild.id)
        if not boss_data:
            return await ctx.send("Không có World Boss nào đang hoạt động để xóa.", ephemeral=True)
        try:
            channel = self.bot.get_channel(boss_data['channel_id'])
            if channel:
                boss_msg = await channel.fetch_message(boss_data['message_id'])
                await boss_msg.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        await db.delete_boss(ctx.guild.id)
        await db.clear_attackers(ctx.guild.id)
        await ctx.send(f"✅ Đã xóa thành công boss **{boss_data['boss_name']}** và dọn dẹp dữ liệu.", ephemeral=True)

    async def handle_attack(self, interaction: discord.Interaction):
        guild = interaction.guild
        author = interaction.user

        boss_data = await db.get_boss(guild.id)
        if not boss_data:
            view = discord.ui.View.from_message(interaction.message)
            if view:
                for item in view.children:
                    item.disabled = True
                await interaction.message.edit(view=view)
            return await interaction.response.send_message("Boss đã bị tiêu diệt hoặc không tồn tại.", ephemeral=True, delete_after=5)

        attacker_data = await db.get_attacker(guild.id, author.id)
        if attacker_data and attacker_data['last_attack_timestamp']:
            last_attack_time = datetime.datetime.fromisoformat(
                attacker_data['last_attack_timestamp'])
            cooldown_end = last_attack_time + \
                datetime.timedelta(seconds=ATTACK_COOLDOWN_SECONDS)
            if datetime.datetime.now(datetime.timezone.utc) < cooldown_end:
                end_timestamp = int(cooldown_end.timestamp())
                return await interaction.response.send_message(
                    f"⏳ Bạn đang trong thời gian hồi chiêu! Có thể tấn công lại <t:{end_timestamp}:R>.",
                    ephemeral=True
                )

        user_data = await db.get_or_create_user(author.id, guild.id)

        # --- LOGIC TÍNH SÁT THƯƠNG MỚI ---
        base_damage = random.randint(
            50, 150) + (user_data.get('level', 1) * 10)
        perm_bonus_percent = user_data.get('perm_damage_bonus', 0.0)

        final_damage = int(base_damage * (1 + perm_bonus_percent))

        await db.update_boss_hp(guild.id, final_damage)
        await db.log_attack(guild.id, author.id, final_damage)

        response_text = f"💥 Bạn đã tấn công **{boss_data['boss_name']}** và gây ra **{final_damage:,}** sát thương!"
        if perm_bonus_percent > 0:
            response_text += f"\n*Nhờ có Linh Dược, sát thương của bạn được tăng **{perm_bonus_percent:.0%}**!*"

        await interaction.response.send_message(response_text, ephemeral=True)
        # --- KẾT THÚC LOGIC MỚI ---

        new_boss_data = await db.get_boss(guild.id)
        try:
            boss_msg = interaction.message
            if new_boss_data['current_hp'] <= 0:
                try:
                    await boss_msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass  # Bỏ qua nếu tin nhắn đã bị xóa

                attackers = await db.get_all_attackers(guild.id)
                total_damage = sum(p['total_damage'] for p in attackers)
                if total_damage == 0:
                    await db.delete_boss(guild.id)
                    await db.clear_attackers(guild.id)
                    return

                last_hitter = author
                mvp_data = attackers[0] if attackers else None
                mvp = guild.get_member(
                    mvp_data['user_id']) if mvp_data else None

                victory_embed = discord.Embed(
                    title=f"⚔️ CHIẾN DỊCH TIÊU DIỆT {new_boss_data['boss_name'].upper()} THÀNH CÔNG! ⚔️",
                    description=f"Sau những nỗ lực không ngừng nghỉ, các chiến binh đã hạ gục thành công **{new_boss_data['boss_name']}** và mang về những chiến lợi phẩm giá trị!",
                    color=discord.Color.gold(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )

                reward_pot = new_boss_data['max_hp']
                mvp_bonus_coin = int(reward_pot * 0.10)
                last_hit_bonus_coin = int(reward_pot * 0.05)

                special_rewards_text = ""
                if mvp:
                    await db.update_coins(mvp.id, guild.id, mvp_bonus_coin)
                    special_rewards_text += f"👑 **MVP:** {mvp.mention} `(+{mvp_bonus_coin:,} 🪙)`\n"
                if last_hitter:
                    await db.update_coins(last_hitter.id, guild.id, last_hit_bonus_coin)
                    special_rewards_text += f"💥 **Đòn kết liễu:** {last_hitter.mention} `(+{last_hit_bonus_coin:,} 🪙)`"

                victory_embed.add_field(
                    name="✨─── VINH DANH ANH HÙNG ───✨", value=special_rewards_text, inline=False)

                all_reward_lines = []
                for i, attacker in enumerate(attackers):
                    member = guild.get_member(attacker['user_id'])
                    if not member:
                        continue

                    share = attacker['total_damage'] / total_damage
                    coin_reward = int(reward_pot * share)
                    await db.update_coins(attacker['user_id'], guild.id, coin_reward)
                    xp_reward = int(attacker['total_damage'] / 5)
                    await db.update_user_xp(attacker['user_id'], guild.id, xp_reward)

                    item_reward_text = ""
                    if random.random() < 0.20:
                        droppable_items = {
                            k: v for k, v in SHOP_ITEMS.items() if k not in ['lottery_ticket', 'perm_damage_upgrade']}
                        if droppable_items:
                            dropped_item_id = random.choice(
                                list(droppable_items.keys()))
                            await db.add_item_to_inventory(attacker['user_id'], guild.id, dropped_item_id)
                            item_reward_text = f" • 🎁 `{SHOP_ITEMS[dropped_item_id]['name']}`"

                    rank_emoji = {0: '🥇', 1: '🥈', 2: '🥉'}.get(i, f"`#{i+1}`")
                    all_reward_lines.append(
                        f"{rank_emoji} {member.mention}: **{coin_reward:,}** 🪙, **{xp_reward:,}** ⭐{item_reward_text}")

                per_page = 10
                initial_page_content = "\n".join(all_reward_lines[:per_page])
                victory_embed.add_field(
                    name="💰─── BẢNG CHIẾN LỢI PHẨM ───💰", value=initial_page_content, inline=False)

                view = VictoryLeaderboardView(
                    victory_embed, all_reward_lines, per_page)
                victory_embed.set_footer(text=f"Trang 1/{view.max_pages}")

                try:
                    # Đây là dòng quan trọng, nó đảm bảo tin nhắn được gửi vào đúng kênh đã diễn ra tương tác
                    await interaction.channel.send(embed=victory_embed, view=view if view.max_pages > 1 else None)
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"Lỗi khi gửi tin nhắn chiến thắng boss: {e}")

                await db.delete_boss(guild.id)
                await db.clear_attackers(guild.id)

            else:
                attackers = await db.get_all_attackers(guild.id)
                new_embed = create_boss_embed(
                    guild, new_boss_data, attackers_data=attackers)
                await boss_msg.edit(embed=new_embed)
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"Lỗi khi cập nhật tin nhắn boss: {e}")
            pass


async def setup(bot):
    await bot.add_cog(Boss(bot))
