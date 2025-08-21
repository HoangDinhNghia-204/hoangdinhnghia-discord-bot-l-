# cogs/blackjack.py
import discord
from discord.ext import commands
import random
import asyncio
import database as db
from .utils import checks  # Thêm import này nếu chưa có
from discord import app_commands

# =============================================================
# IMPORT VIEW TỪ COG FUN
# =============================================================
try:
    # Cố gắng import view từ file fun.py
    from .fun import CreateNewLobbyView
except (ImportError, SystemError):
    # Fallback: Định nghĩa lại class nếu import thất bại (giúp bot không bị crash)
    class CreateNewLobbyView(discord.ui.View):
        def __init__(self, *args, **kwargs):
            super().__init__(timeout=1.0)
            print(
                "WARNING: Could not import CreateNewLobbyView from fun.py. Blackjack replay disabled.")

# =============================================================
# CÁC HÀM, VIEW, MODAL CỦA BLACKJACK
# =============================================================

RANKS = {"A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
         "7": 7, "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10}


def create_deck():
    deck = list(RANKS.keys()) * 4
    random.shuffle(deck)
    return deck


def calculate_score(hand):
    score = sum(RANKS[card] for card in hand)
    num_aces = hand.count('A')
    while score > 21 and num_aces > 0:
        score -= 10
        num_aces -= 1
    return score


def format_hand(hand): return ' '.join([f'`[{card}]`' for card in hand])


class BlackjackGameView(discord.ui.View):
    def __init__(self, players: list[discord.Member], bet_amount: int, message: discord.Message, cog, original_ctx):
        super().__init__(timeout=300.0)
        self.players, self.bet_amount, self.message, self.cog, self.original_ctx = players, bet_amount, message, cog, original_ctx
        self.deck = create_deck()
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.player_states = {p.id: {"member": p, "hand": [self.deck.pop(
        ), self.deck.pop()], "status": "playing", "score": 0} for p in self.players}
        self.current_player_index = 0

    async def interaction_check(self, i: discord.Interaction):
        if i.data.get('custom_id') == "view_hand_button":
            return i.user.id in self.player_states
        if self.is_finished() or self.current_player_index >= len(self.players):
            return False
        if i.user.id != self.players[self.current_player_index].id:
            await i.response.send_message("Chưa đến lượt của bạn.", ephemeral=True)
            return False
        return True

    def create_game_embed(self, show_dealer_hand=False, final_results=None) -> discord.Embed:
        if final_results:
            title, description = "🃏 KẾT QUẢ VÁN BÀI 🃏", "So bài với nhà cái!"
        else:
            current_player = self.players[self.current_player_index] if self.current_player_index < len(
                self.players) else None
            title = f"🃏 Xì Dách - Cược {self.bet_amount:,} Coin"
            description = f"Đến lượt của {current_player.mention if current_player else 'Nhà Cái'}!"
        embed = discord.Embed(
            title=title, description=description, color=discord.Color.gold())
        dealer_score = calculate_score(self.dealer_hand)
        dealer_hand_display = ' '.join(
            [f'`[{self.dealer_hand[0]}]`', '`[??]`']) if not show_dealer_hand else format_hand(self.dealer_hand)
        embed.add_field(
            name=f"Bài Nhà Cái ({dealer_score if show_dealer_hand else ''})", value=dealer_hand_display, inline=False)
        player_info = ""
        for p_id, state in self.player_states.items():
            status_emoji = ""
            if state['status'] == 'playing' and self.current_player_index < len(self.players) and p_id == self.players[self.current_player_index].id:
                status_emoji = "▶️ "
            elif state['status'] == 'stand':
                status_emoji = "✋ "
            elif state['status'] == 'bust':
                status_emoji = "💥 "
            elif state['status'] == 'blackjack':
                status_emoji = "✨ "
            hand_display = f"({state['score']}) - {format_hand(state['hand'])}" if show_dealer_hand else f"({len(state['hand'])} lá)"
            player_info += f"{status_emoji}**{state['member'].display_name}:** {hand_display}\n"
        embed.add_field(name="--- Người Chơi ---",
                        value=player_info, inline=False)
        if final_results:
            embed.add_field(name="--- Kết Quả Chi Tiết ---",
                            value=final_results, inline=False)
        return embed

    async def next_turn(self):
        self.current_player_index += 1
        if self.current_player_index < len(self.players):
            await self.message.edit(embed=self.create_game_embed(), view=self)
        else:
            for item in self.children:
                item.disabled = True
            dealer_turn_embed = self.create_game_embed()
            dealer_turn_embed.description = "Lượt người chơi đã xong. **Đến lượt Nhà Cái!**"
            await self.message.edit(embed=dealer_turn_embed, view=self)
            await asyncio.sleep(2)
            asyncio.create_task(self.dealer_turn())

    async def start_game(self):
        for p_id, state in self.player_states.items():
            state["score"] = calculate_score(state["hand"])
            if state["score"] == 21:
                state["status"] = "blackjack"
        while self.current_player_index < len(self.players) and self.player_states[self.players[self.current_player_index].id]["status"] != "playing":
            self.current_player_index += 1
        if self.current_player_index >= len(self.players):
            asyncio.create_task(self.dealer_turn())
        else:
            await self.message.edit(embed=self.create_game_embed(), view=self)

    async def dealer_turn(self):
        self.stop()
        for item in self.children:
            item.disabled = True
        await self.message.edit(embed=self.create_game_embed(show_dealer_hand=True), view=self)
        await asyncio.sleep(1.5)
        dealer_score = calculate_score(self.dealer_hand)
        while dealer_score < 17:
            self.dealer_hand.append(self.deck.pop())
            dealer_score = calculate_score(self.dealer_hand)
            await self.message.edit(embed=self.create_game_embed(show_dealer_hand=True))
            await asyncio.sleep(1.5)
        await self.resolve_game()

    async def resolve_game(self):
        dealer_score = calculate_score(self.dealer_hand)
        result_text = ""
        for p_id, state in self.player_states.items():
            # Thêm p_hand
            member, p_score, p_hand = state["member"], state["score"], state["hand"]
            result = ""

            # --- PHẦN SỬA LỖI VÀ THÊM LUẬT NGŨ LINH ---

            # 1. Kiểm tra Ngũ Linh trước
            is_ngu_linh = len(p_hand) >= 5 and p_score <= 21

            if state["status"] == "bust":
                result = f"💔 **Thua** (Quắc!) - Mất {self.bet_amount:,} coin."

            # 2. Xử lý Ngũ Linh
            elif is_ngu_linh:
                # Ngũ Linh chỉ thua Blackjack (2 lá 21 điểm)
                if dealer_score == 21 and len(self.dealer_hand) == 2:
                    result = f"💔 **Thua** (Nhà cái có Blackjack!) - Mất {self.bet_amount:,} coin."
                else:
                    payout = self.bet_amount * 3  # Thưởng Ngũ Linh x3
                    result = f"🐲 **NGŨ LINH!** - Nhận {payout:,} coin."
                    await db.update_coins(member.id, member.guild.id, payout)
                    await self.update_win_stats(member)

            elif state["status"] == "blackjack":
                # Sửa lại để chỉ hòa với Blackjack
                if dealer_score == 21 and len(self.dealer_hand) == 2:
                    result = f"🤝 **Hòa** - Hoàn lại {self.bet_amount:,} coin."
                    await db.update_coins(member.id, member.guild.id, self.bet_amount)
                else:
                    payout = int(self.bet_amount * 2.5)
                    result = f"✨ **BLACKJACK!** - Nhận {payout:,} coin."
                    await db.update_coins(member.id, member.guild.id, payout)
                    await self.update_win_stats(member)
            elif dealer_score > 21:
                payout = self.bet_amount * 2
                # Thêm lý do
                result = f"🎉 **Thắng** (Nhà cái Quắc!) - Nhận {payout:,} coin."
                await db.update_coins(member.id, member.guild.id, payout)
                await self.update_win_stats(member)
            elif p_score > dealer_score:
                payout = self.bet_amount * 2
                # Thêm lý do
                result = f"🎉 **Thắng** ({p_score} > {dealer_score}) - Nhận {payout:,} coin."
                await db.update_coins(member.id, member.guild.id, payout)
                await self.update_win_stats(member)
            elif p_score < dealer_score:
                # Thêm lý do
                result = f"💔 **Thua** ({p_score} < {dealer_score}) - Mất {self.bet_amount:,} coin."
            else:
                # Thêm lý do
                result = f"🤝 **Hòa** ({p_score} = {dealer_score}) - Hoàn lại {self.bet_amount:,} coin."
                await db.update_coins(member.id, member.guild.id, self.bet_amount)

            result_text += f"**{member.display_name}:** {result}\n"

        final_embed = self.create_game_embed(
            show_dealer_hand=True, final_results=result_text)
        new_lobby_view = CreateNewLobbyView(
            self.cog, self.original_ctx, 'blackjack', self.bet_amount)
        await self.message.edit(embed=final_embed, view=new_lobby_view)

    async def update_win_stats(self, member: discord.Member):
        await db.update_quest_progress(member.id, member.guild.id, 'BLACKJACK_WIN')
        unlocked_ach = await db.update_achievement_progress(member.id, member.guild.id, 'BLACKJACK_WIN')
        if unlocked_ach:
            for ach in unlocked_ach:
                try:
                    await self.message.channel.send(f"🏆 {member.mention} mở khóa thành tựu: **{ach['name']}**! (+{ach['reward_coin']:,} coin, +{ach['reward_xp']} XP)", delete_after=30)
                except:
                    pass

    @discord.ui.button(label="Rút Bài", style=discord.ButtonStyle.green, emoji="➕")
    async def hit(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.defer()
        p_state = self.player_states[i.user.id]
        p_state["hand"].append(self.deck.pop())
        p_state["score"] = calculate_score(p_state["hand"])
        if p_state["score"] > 21:
            p_state["status"] = "bust"
            await self.next_turn()
        else:
            await self.message.edit(embed=self.create_game_embed())

    @discord.ui.button(label="Dằn Bài", style=discord.ButtonStyle.red, emoji="✋")
    async def stand(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.defer()
        self.player_states[i.user.id]["status"] = "stand"
        await self.next_turn()

    @discord.ui.button(label="Xem Bài", style=discord.ButtonStyle.secondary, emoji="👁️", row=1, custom_id="view_hand_button")
    async def view_hand(self, i: discord.Interaction, b: discord.ui.Button):
        p_state = self.player_states.get(i.user.id)
        if not p_state:
            return await i.response.send_message("Bạn không trong ván bài này.", ephemeral=True)
        await i.response.send_message(f"Bài của bạn: {format_hand(p_state['hand'])}\nĐiểm: **{p_state['score']}**", ephemeral=True)


class BlackjackLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member, bet_amount: int, cog):
        super().__init__(timeout=120.0)
        self.host, self.bet_amount, self.cog = host, bet_amount, cog
        self.players = {host}
        self.message = None
        self.original_ctx = None

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🃏 Bàn Cược Xì Dách - Cược {self.bet_amount:,} Coin 🃏",
                              description="Nhấn **Tham Gia**!", color=discord.Color.dark_green())
        embed.add_field(name=f"Người chơi ({len(self.players)})", value="\n".join(
            [p.mention for p in self.players]) or "Chưa có ai.")
        embed.set_footer(
            text=f"Chủ xị ({self.host.display_name}) có thể bắt đầu/hủy.")
        return embed

    @discord.ui.button(label="Tham Gia", emoji="🎟️")
    async def join(self, i: discord.Interaction, b: discord.ui.Button):
        if i.user in self.players:
            return await i.response.send_message("Bạn đã tham gia.", ephemeral=True)
        user_data = await db.get_or_create_user(i.user.id, i.guild.id)
        if user_data['coins'] < self.bet_amount:
            return await i.response.send_message(f"Không đủ **{self.bet_amount:,}** coin.", ephemeral=True)
        self.players.add(i.user)
        await i.response.edit_message(embed=self.create_embed())

    @discord.ui.button(label="Bắt Đầu", emoji="▶️")
    async def start(self, i: discord.Interaction, b: discord.ui.Button):
        if i.user.id != self.host.id:
            return await i.response.send_message("Chỉ chủ xị có thể bắt đầu.", ephemeral=True)
        if len(self.players) < 1:
            return await i.response.send_message("Cần ít nhất 1 người chơi.", ephemeral=True)
        await i.response.defer()
        self.stop()
        for player in self.players:
            await db.update_coins(player.id, i.guild.id, -self.bet_amount)
        game_view = BlackjackGameView(
            list(self.players), self.bet_amount, self.message, self.cog, self.original_ctx)
        await game_view.start_game()

    @discord.ui.button(label="Hủy", emoji="✖️")
    async def cancel(self, i: discord.Interaction, b: discord.ui.Button):
        if i.user.id != self.host.id:
            return await i.response.send_message("Chỉ chủ xị có thể hủy.", ephemeral=True)
        embed = self.create_embed()
        embed.title = "[ĐÃ HỦY] " + embed.title
        embed.description = "Bàn cược đã hủy."
        embed.color = discord.Color.dark_grey()
        [setattr(c, 'disabled', True) for c in self.children]
        await i.response.edit_message(embed=embed, view=None)
        self.stop()


class Blackjack(commands.Cog):
    """🃏 Trò chơi Xì Dách (Blackjack) nhiều người chơi."""
    COG_EMOJI = "🃏"
    def __init__(self, bot): self.bot = bot

    async def cog_check(self, ctx: commands.Context):
        config = await db.get_or_create_config(ctx.guild.id)
        if (debtor_role_id := config.get('debtor_role_id')) and (debtor_role := ctx.guild.get_role(debtor_role_id)) and debtor_role in ctx.author.roles:
            await ctx.send("Bạn đang trong tình trạng vỡ nợ!", ephemeral=True, delete_after=10)
            return False
        return True

    @commands.hybrid_command(name="blackjack", aliases=['bj'], description="Tạo bàn cược Xì Dách cho nhiều người.")
    @app_commands.rename(bet_amount="số_tiền_cược")
    async def blackjack_table(self, ctx: commands.Context, bet_amount: int):
        if bet_amount <= 0:
            return await ctx.send("Tiền cược phải lớn hơn 0.", ephemeral=True)
        host_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if host_data['coins'] < bet_amount:
            return await ctx.send(f"Bạn không đủ **{bet_amount:,}** coin.", ephemeral=True)

        lobby_view = BlackjackLobbyView(ctx.author, bet_amount, self)
        # --- PHẦN NÂNG CẤP ---
        lobby_view.original_ctx = ctx  # Lưu context để tạo lại bàn mới

        lobby_embed = lobby_view.create_embed()
        lobby_view.message = await ctx.send(embed=lobby_embed, view=lobby_view)


async def setup(bot):
    await bot.add_cog(Blackjack(bot))
