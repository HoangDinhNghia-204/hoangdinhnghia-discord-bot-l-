# cogs/tasks.py
import discord
from discord.ext import commands, tasks
import database as db
import datetime
import random
import itertools
import asyncio
import json


class BackgroundTasks(commands.Cog):
    """Cog chứa các tác vụ chạy nền của bot."""

    def __init__(self, bot):
        self.bot = bot
        self.role_update_lock = asyncio.Lock()
        self.last_weekly_reward_day = None

        # Tạo đối tượng múi giờ cho Việt Nam (UTC+7) để sử dụng trong các task
        self.VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

        self.rainbow_color_cycle = itertools.cycle([
            discord.Color.from_rgb(255, 20, 147),    # Deep Pink
            discord.Color.from_rgb(255, 0, 255),     # Magenta
            discord.Color.from_rgb(148, 0, 211),     # Dark Violet
            discord.Color.from_rgb(75, 0, 130),      # Indigo
            discord.Color.from_rgb(30, 144, 255),    # Dodger Blue
            discord.Color.from_rgb(0, 191, 255),     # Deep Sky Blue
            discord.Color.from_rgb(0, 255, 255),     # Cyan / Aqua
            discord.Color.from_rgb(0, 255, 127),     # Spring Green
            discord.Color.from_rgb(50, 205, 50),     # Lime Green
            discord.Color.from_rgb(255, 255, 0),     # Yellow
            discord.Color.from_rgb(255, 165, 0),     # Orange
            discord.Color.from_rgb(255, 69, 0),      # Red-Orange
            discord.Color.from_rgb(255, 173, 173),   # Pastel Red
            discord.Color.from_rgb(255, 214, 165),   # Pastel Orange
            discord.Color.from_rgb(253, 255, 182),   # Pastel Yellow
            discord.Color.from_rgb(202, 255, 191),   # Pastel Green
            discord.Color.from_rgb(155, 246, 255),   # Pastel Cyan
            discord.Color.from_rgb(160, 196, 255),   # Pastel Blue
            discord.Color.from_rgb(189, 178, 255),   # Pastel Indigo
            discord.Color.from_rgb(255, 198, 255),   # Pastel Pink/Violet
        ])

        # Bắt đầu tất cả các task
        self.check_expirations.start()
        self.weekly_leaderboard_reward.start()
        self.check_overdue_loans.start()
        self.assign_daily_quests.start()
        self.rainbow_role_task.start()
        self.check_expired_trivia.start()

    def cog_unload(self):
        for task in [self.check_expirations, self.weekly_leaderboard_reward, self.check_overdue_loans, self.assign_daily_quests, self.rainbow_role_task, self.check_expired_trivia]:
            task.cancel()

    # ===============================================
    # Task đổi màu Cầu vồng
    # ===============================================
    @tasks.loop(seconds=30.0)# Tần suất chạy bình thường
    async def rainbow_role_task(self):
        if self.role_update_lock.locked():
            return

        async with self.role_update_lock:
            try:
                next_color = next(self.rainbow_color_cycle)
                for guild in self.bot.guilds:
                    try:
                        config = await db.get_or_create_config(guild.id)
                        rainbow_role_id = config.get('rainbow_role_id')
                        if rainbow_role_id:
                            role = guild.get_role(rainbow_role_id)
                            if role and role.color != next_color:
                                await role.edit(color=next_color, reason="Hiệu ứng rainbow")
                    except discord.HTTPException as e:
                        if e.status == 429:  # Lỗi Rate Limit
                            print(
                                "-> WARNING: Bị Rate Limit! Tạm dừng task đổi màu trong 5 phút.")
                            self.rainbow_role_task.change_interval(minutes=5)
                            # Sau khi đổi interval, nó sẽ tự động chạy lại sau 5 phút
                        else:
                            print(f"-> LỖI HTTP KHI EDIT ROLE: {e}")
                    except Exception as edit_error:
                        print(f"-> LỖI KHÁC KHI EDIT ROLE: {edit_error}")

                # Nếu không có lỗi, đảm bảo task chạy ở tần suất bình thường
                # Trở lại 30 giây sau khi hồi phục từ rate limit
                if getattr(self.rainbow_role_task, 'seconds', None) != 30.0:
                    self.rainbow_role_task.change_interval(seconds=30.0)

            except Exception as e:
                print(
                    f"[CRITICAL TASK ERROR] Task rainbow_role_task đã gặp lỗi: {e}")

    @rainbow_role_task.before_loop
    async def before_rainbow_task(self):
        await self.bot.wait_until_ready()

    # ===============================================
    # Task kiểm tra hết hạn
    # ===============================================
    @tasks.loop(minutes=1)
    async def check_expirations(self):
        if self.role_update_lock.locked():
            return
        async with self.role_update_lock:
            try:
                expired_roles = await db.get_expired_items('temporary_roles')
                if expired_roles:
                    items_to_clear = []
                    for item in expired_roles:
                        guild = self.bot.get_guild(item['guild_id'])
                        if not guild:
                            items_to_clear.append(item)
                            continue
                        role = guild.get_role(item['role_id'])
                        if not role:
                            items_to_clear.append(item)
                            continue
                        try:
                            member = await guild.fetch_member(item['user_id'])
                            if member and role in member.roles:
                                await member.remove_roles(role, reason="Role đã mua/bị phạt đã hết hạn.")
                        except (discord.NotFound, discord.Forbidden):
                            pass
                        except Exception as e:
                            print(f" ! Error removing temporary role: {e}")
                        items_to_clear.append(item)
                    if items_to_clear:
                        await db.clear_expired_items('temporary_roles', ['user_id', 'guild_id', 'role_id'], items_to_clear)
                expired_effects = await db.get_expired_items('active_effects')
                if expired_effects:
                    await db.clear_expired_items('active_effects', ['user_id', 'guild_id', 'effect_type'], expired_effects)
            except Exception as e:
                print(
                    f"[CRITICAL TASK ERROR] Task check_expirations đã gặp lỗi: {e}")

    @check_expirations.before_loop
    async def before_check_expirations(self):
        await self.bot.wait_until_ready()

    # ===============================================
    # Task trao thưởng BXH Tuần
    # ===============================================
    # Chạy task vào 8:00 sáng mỗi ngày theo giờ Việt Nam (UTC+7)
        # ===============================================
    # Task trao thưởng BXH Tuần (PHIÊN BẢN CẢI TIẾN)
    # ===============================================
    # Chạy mỗi giờ để kiểm tra, nhưng chỉ thực hiện logic vào đúng thời điểm
    @tasks.loop(hours=1)
    async def weekly_leaderboard_reward(self):
        now_vn = datetime.datetime.now(self.VN_TZ)

        # Điều kiện 1: Phải là Thứ Hai
        is_monday = (now_vn.weekday() == 0)
        
        # Điều kiện 2: Phải sau 8 giờ sáng
        is_after_8am = (now_vn.hour >= 8)

        # Điều kiện 3: Tuần này chưa trao thưởng
        # Lấy số tuần trong năm để định danh
        current_week_identifier = now_vn.strftime('%Y-%W') 
        has_rewarded_this_week = (self.last_weekly_reward_day == current_week_identifier)

        # Nếu không phải là thời điểm trao thưởng, thoát ra
        if not (is_monday and is_after_8am and not has_rewarded_this_week):
            return

        # Nếu là thời điểm trao thưởng, nhưng bị khóa, chỉ in ra và chờ lần chạy sau (sau 1 tiếng)
        if self.role_update_lock.locked():
            print(f"[{now_vn}] Định trao thưởng tuần nhưng đang bị khóa. Sẽ thử lại sau 1 giờ.")
            return

        # Nếu tất cả điều kiện đều ổn, tiến hành trao thưởng
        async with self.role_update_lock:
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            print(f"[{utc_now}] === RUNNING WEEKLY LEADERBOARD REWARD TASK ===")
            try:
                # ... (TOÀN BỘ LOGIC TRAO THƯỞNG CỦA BẠN GIỮ NGUYÊN Ở ĐÂY) ...
                for guild in self.bot.guilds:
                    try:
                        config = await db.get_or_create_config(guild.id)
                        top_role_id = config.get('top_role_id')
                        if not top_role_id or not (top_role := guild.get_role(top_role_id)):
                            continue

                        old_winners = list(top_role.members)
                        for member in old_winners:
                            try:
                                await member.remove_roles(top_role, reason="Kết thúc nhiệm kỳ Top 1 tuần")
                            except discord.HTTPException as e:
                                print(f"     ! Lỗi khi xóa role của {member.display_name}: {e}")

                        leaderboard = await db.get_leaderboard(guild.id, limit=1)
                        if not leaderboard:
                            continue

                        new_winner_id = leaderboard[0]['user_id']
                        try:
                            new_winner = await guild.fetch_member(new_winner_id)
                            if top_role not in new_winner.roles:
                                await new_winner.add_roles(top_role, reason="Đạt Top 1 Leaderboard tuần")

                            if (announce_channel_id := config.get('announcement_channel_id')) and (channel := self.bot.get_channel(announce_channel_id)):
                                embed = discord.Embed(title="🏆 VINH DANH TOP 1 BẢNG XẾP HẠNG TUẦN 🏆",
                                                      description=f"Xin chúc mừng {new_winner.mention} đã xuất sắc thống trị bảng xếp hạng tuần này và nhận được danh hiệu cao quý {top_role.mention}!",
                                                      color=top_role.color or discord.Color.gold(),
                                                      timestamp=utc_now)
                                embed.set_thumbnail(url=new_winner.display_avatar.url)
                                embed.set_footer(text="Một tuần mới, một cuộc đua mới lại bắt đầu!")
                                await channel.send(embed=embed)

                        except (discord.NotFound, discord.Forbidden) as e:
                            print(f"   ! Không thể xử lý người thắng cuộc cho guild '{guild.name}': {e}")
                    except Exception as e:
                        print(f"   ! Lỗi không mong muốn trong lúc trao thưởng cho guild '{guild.name}': {e}")

                # Đánh dấu là đã trao thưởng cho tuần này thành công
                self.last_weekly_reward_day = current_week_identifier
                print(f"[{utc_now}] === WEEKLY LEADERBOARD REWARD TASK COMPLETED SUCCESSFULLY ===")

            except Exception as e:
                print(f"[CRITICAL TASK ERROR] Task weekly_leaderboard_reward đã thất bại: {e}")

    @weekly_leaderboard_reward.before_loop
    async def before_weekly_leaderboard_reward(self):
        await self.bot.wait_until_ready()

    # ===============================================
    # Task kiểm tra nợ quá hạn
    # ===============================================
    @tasks.loop(minutes=5)
    async def check_overdue_loans(self):
        if self.role_update_lock.locked():
            return
        async with self.role_update_lock:
            try:
                print(f"[{datetime.datetime.now()}] Running overdue loans check...")
                now = datetime.datetime.now(datetime.timezone.utc)
                all_loans = await db.get_all_loans()
                for loan in all_loans:
                    if now > datetime.datetime.fromisoformat(loan['due_date']):
                        guild = self.bot.get_guild(loan['guild_id'])
                        if not guild:
                            continue
                        config = await db.get_or_create_config(guild.id)
                        if not (debtor_role_id := config.get('debtor_role_id')) or not (debtor_role := guild.get_role(debtor_role_id)):
                            continue
                        try:
                            member = await guild.fetch_member(loan['user_id'])
                            if debtor_role not in member.roles:
                                await member.add_roles(debtor_role, reason="Quá hạn trả nợ")
                        except discord.NotFound:
                            await db.delete_loan(loan['user_id'], loan['guild_id'])
                        except discord.Forbidden:
                            print(
                                f"Bot cannot apply debtor role in {guild.name}")
            except Exception as e:
                print(
                    f"[CRITICAL TASK ERROR] Task check_overdue_loans đã gặp lỗi: {e}")

    @check_overdue_loans.before_loop
    async def before_check_loans(self):
        await self.bot.wait_until_ready()

    # ===============================================
    # Task giao nhiệm vụ hàng ngày
    # ===============================================
    @tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=datetime.timezone.utc))
    # @tasks.loop(minutes=1)
    async def assign_daily_quests(self):
        try:
            daily_quests = await db.get_quests_by_frequency('DAILY')
            if not daily_quests:
                return
            today_str = datetime.date.today().isoformat()
            num_quests_to_assign = 8
            for guild in self.bot.guilds:
                if len(daily_quests) < num_quests_to_assign:
                    num_quests_to_assign = len(daily_quests)
                for member in guild.members:
                    if member.bot:
                        continue
                    current_quests = await db.get_user_quests(member.id, guild.id)
                    if not current_quests or current_quests[0]['assigned_date'] != today_str:
                        quests_for_this_member = random.sample(
                            daily_quests, min(num_quests_to_assign, len(daily_quests)))
                        quest_ids = [q['quest_id']
                                     for q in quests_for_this_member]
                        await db.assign_user_quests(member.id, guild.id, quest_ids, today_str)
        except Exception as e:
            print(
                f"[CRITICAL TASK ERROR] Task assign_daily_quests đã gặp lỗi: {e}")

    @assign_daily_quests.before_loop
    async def before_assign_quests(self):
        await self.bot.wait_until_ready()
        
    @tasks.loop(minutes=5)
    async def check_expired_trivia(self):
        try:
            expired_sessions = await db.get_expired_trivia()
            if not expired_sessions:
                return

            for session in expired_sessions:
                try:
                    channel = self.bot.get_channel(session['channel_id']) or await self.bot.fetch_channel(session['channel_id'])
                    message = await channel.fetch_message(session['message_id'])

                    # Tạo một view mới đã bị vô hiệu hóa dựa trên các nút gốc của tin nhắn
                    view = discord.ui.View()
                    correct = session['correct_answer']
                    try:
                        # Cố gắng đọc lại các nhãn nút từ message.components
                        if message.components:
                            for action_row in message.components:
                                # discord.ActionRow có thể có thuộc tính children
                                components = getattr(action_row, 'children', None) or getattr(action_row, 'components', [])
                                for comp in components:
                                    label = getattr(comp, 'label', None)
                                    if not label:
                                        continue
                                    style = discord.ButtonStyle.green if label == correct else discord.ButtonStyle.secondary
                                    view.add_item(discord.ui.Button(label=label, style=style, disabled=True))
                        else:
                            # Không có components: tạo tối thiểu một nút hiển thị đáp án đúng
                            view.add_item(discord.ui.Button(label=correct, style=discord.ButtonStyle.green, disabled=True))
                    except Exception:
                        # Phòng thủ: nếu không đọc được components, vẫn hiển thị đáp án đúng
                        view.add_item(discord.ui.Button(label=correct, style=discord.ButtonStyle.green, disabled=True))

                    # Cập nhật tin nhắn
                    original_embed = message.embeds[0]
                    original_embed.set_footer(text=f"Đã hết giờ! Đáp án đúng là: {session['correct_answer']}")
                    original_embed.color = discord.Color.dark_grey()

                    await message.edit(embed=original_embed, view=view)

                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                    print(f"[Trivia Task] Lỗi khi xử lý tin nhắn hết hạn {session['message_id']}: {e}")
                finally:
                    # Luôn xóa khỏi DB để tránh xử lý lại
                    await db.remove_active_trivia(session['message_id'])

        except Exception as e:
            print(f"[CRITICAL TASK ERROR] Task check_expired_trivia đã gặp lỗi: {e}")

    @check_expired_trivia.before_loop
    async def before_check_expired_trivia(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(BackgroundTasks(bot))
