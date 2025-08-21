# cogs/auction.py
import discord
from discord.ext import commands, tasks
import datetime
import re
from typing import Union
import database as db
from .utils import checks
from discord import app_commands


def parse_duration(duration_str: str) -> datetime.timedelta:
    match = re.match(r"(\d+)([mhd])", duration_str.lower())
    if not match:
        raise ValueError(
            "Định dạng thời gian không hợp lệ. Ví dụ: `1h`, `3d`, `30m`.")
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        return datetime.timedelta(minutes=value)
    if unit == 'h':
        return datetime.timedelta(hours=value)
    if unit == 'd':
        return datetime.timedelta(days=value)
    return None


class Auction(commands.Cog):
    """🔨 Hệ thống đấu giá vật phẩm."""
    COG_EMOJI = "🔨"

    def __init__(self, bot):
        self.bot = bot
        self.check_finished_auctions.start()

    def cog_unload(self):
        self.check_finished_auctions.cancel()

    async def cog_check(self, ctx: commands.Context):
        """Kiểm tra chung cho tất cả các lệnh trong Cog này."""
        config = await db.get_or_create_config(ctx.guild.id)
        if debtor_role_id := config.get('debtor_role_id'):
            if debtor_role := ctx.guild.get_role(debtor_role_id):
                if debtor_role in ctx.author.roles:
                    await ctx.send("Bạn đang trong tình trạng vỡ nợ và không thể sử dụng lệnh này! Dùng `?trano` để trả nợ.", delete_after=10, ephemeral=True)
                    return False
        return True

    # BỎ DECORATOR QUYỀN Ở ĐÂY
    @commands.hybrid_group(name="auction", description="Nhóm lệnh quản lý đấu giá.", default_permissions=discord.Permissions(manage_guild=True))
    async def auction(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    # THÊM DECORATOR QUYỀN VÀO ĐÂY
    # cogs/auction.py -> class Auction

    @auction.command(name="start", description="Bắt đầu một phiên đấu giá cho Role hoặc vật phẩm ảo.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(item_to_auction="vật_phẩm", start_price="giá_khởi_điểm", duration_str="thời_gian")
    async def auction_start(self, ctx: commands.Context, item_to_auction: str, start_price: int, duration_str: str):
        if start_price < 0:
            return await ctx.send("Giá khởi điểm không thể âm.", delete_after=10, ephemeral=True)

        item_is_role = False
        try:
            role_converter = commands.RoleConverter()
            role = await role_converter.convert(ctx, item_to_auction)
            item_is_role = True
        except commands.RoleNotFound:
            role = None

        if item_is_role:
            item_type, item_id, item_name, display_name = 'ROLE', role.id, role.name, role.mention
        else:
            item_type, item_id, item_name, display_name = 'VIRTUAL', None, item_to_auction, item_to_auction

        try:
            duration = parse_duration(duration_str)
        except ValueError as e:
            return await ctx.send(str(e), delete_after=15, ephemeral=True)

        end_time = datetime.datetime.now(datetime.timezone.utc) + duration
        end_timestamp = int(end_time.timestamp())

        embed = discord.Embed(
            title="🔨 PHIÊN ĐẤU GIÁ MỚI",
            description=f"**Vật phẩm:** {display_name}\n\nMột vật phẩm cực phẩm đã lên sàn! Cơ hội duy nhất để sở hữu!",
            color=discord.Color.gold()
        )
        embed.set_author(
            name=f"Người bán: {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="💰 Giá khởi điểm",
                        value=f"**{start_price:,}** coin", inline=True)
        embed.add_field(name="📈 Giá hiện tại",
                        value=f"**{start_price:,}** coin", inline=True)
        embed.add_field(name="👑 Người giữ giá",
                        value="*Chưa có ai trả giá*", inline=False)
        embed.add_field(name="⏳ Kết thúc sau",
                        value=f"<t:{end_timestamp}:R> (vào lúc <t:{end_timestamp}:F>)", inline=False)
        embed.set_footer(
            text="Dùng lệnh /bid <số tiền> <message_id> để đấu giá.")

        # =============================================================
        # <<< PHẦN SỬA LỖI LOGIC PHẢN HỒI >>>
        # =============================================================
        if ctx.interaction:
            # Nếu là Slash Command, gửi phản hồi ban đầu
            await ctx.interaction.response.send_message(embed=embed)
            # Lấy tin nhắn vừa gửi để có ID
            auction_msg = await ctx.interaction.original_response()
            # Gửi tin nhắn chứa ID bằng followup
            await ctx.interaction.followup.send(f"ID phiên đấu giá để bid: `{auction_msg.id}`", ephemeral=True)
        else:
            # Nếu là Prefix Command, hoạt động như cũ
            auction_msg = await ctx.send(embed=embed)
            await ctx.channel.send(f"ID phiên đấu giá: `{auction_msg.id}`", delete_after=60)
        # =============================================================

        await db.create_auction(
            guild_id=ctx.guild.id, channel_id=ctx.channel.id, message_id=auction_msg.id,
            item_name=item_name, item_type=item_type, item_id=item_id,
            seller_id=ctx.author.id, start_price=start_price, end_timestamp_str=end_time.isoformat()
        )

    # THÊM DECORATOR QUYỀN VÀO ĐÂY
    @auction.command(name="cancel", description="Hủy một phiên đấu giá đang diễn ra.")
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(auction_message_id="id_tin_nhắn_đấu_giá")
    async def auction_cancel(self, ctx: commands.Context, auction_message_id: str):
        try:
            message_id = int(auction_message_id)
        except ValueError:
            return await ctx.send("ID tin nhắn không hợp lệ.", ephemeral=True)

        auction = await db.get_auction(message_id)
        if not auction or not auction['is_active']:
            return await ctx.send("Đây không phải là một phiên đấu giá đang hoạt động.", delete_after=10, ephemeral=True)

        if highest_bidder_id := auction.get('highest_bidder_id'):
            await db.update_coins(highest_bidder_id, ctx.guild.id, auction['current_bid'])

        await db.end_auction(auction['message_id'])

        try:
            auction_msg = await ctx.channel.fetch_message(auction['message_id'])
            original_embed = auction_msg.embeds[0]
            original_embed.title = f"[ĐÃ HỦY] {original_embed.title}"
            original_embed.description = f"Phiên đấu giá đã bị hủy bởi {ctx.author.mention}."
            original_embed.color = discord.Color.dark_red()
            original_embed.clear_fields()
            original_embed.add_field(name="Trạng thái", value="Đã hủy")
            await auction_msg.edit(embed=original_embed)
        except (discord.NotFound, discord.HTTPException):
            pass

        await ctx.send(f"✅ Đã hủy thành công phiên đấu giá.", delete_after=10, ephemeral=True)

    @commands.hybrid_command(name="bid", description="Trả giá cho một phiên đấu giá.")
    @app_commands.rename(amount="số_tiền", auction_message_id="id_tin_nhắn_đấu_giá")
    async def bid(self, ctx: commands.Context, amount: int, auction_message_id: str):
        try:
            message_id = int(auction_message_id)
        except ValueError:
            return await ctx.send("ID tin nhắn không hợp lệ.", ephemeral=True)

        auction = await db.get_auction(message_id)
        if not auction or not auction['is_active']:
            return await ctx.send("Đây không phải là một phiên đấu giá đang hoạt động.", delete_after=10, ephemeral=True)

        if amount <= auction['current_bid']:
            return await ctx.send(f"❌ Giá của bạn phải cao hơn mức giá hiện tại (**{auction['current_bid']:,}** coin).", delete_after=10, ephemeral=True)

        user_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if user_data['coins'] < amount:
            return await ctx.send(f"❌ Bạn không đủ **{amount:,}** coin để trả giá.", delete_after=10, ephemeral=True)

        if highest_bidder_id := auction.get('highest_bidder_id'):
            if ctx.author.id == highest_bidder_id:
                return await ctx.send("❌ Bạn đang là người giữ giá cao nhất rồi.", delete_after=10, ephemeral=True)
            await db.update_coins(highest_bidder_id, ctx.guild.id, auction['current_bid'])

        await db.update_coins(ctx.author.id, ctx.guild.id, -amount)
        await db.update_quest_progress(ctx.author.id, ctx.guild.id, 'BID_AUCTION')
        await db.update_quest_progress(ctx.author.id, ctx.guild.id, 'COIN_SPEND', value_to_add=amount)

        unlocked_bid = await db.update_achievement_progress(ctx.author.id, ctx.guild.id, 'BID_AUCTION')
        if unlocked_bid:
            for ach in unlocked_bid:
                await ctx.channel.send(f"🏆 {ctx.author.mention} vừa mở khóa thành tựu mới: **{ach['name']}**! (+{ach['reward_coin']:,} coin, +{ach['reward_xp']} XP)", delete_after=30)

        unlocked_spend = await db.update_achievement_progress(ctx.author.id, ctx.guild.id, 'COIN_SPEND', value_to_add=amount)
        if unlocked_spend:
            for ach in unlocked_spend:
                await ctx.channel.send(f"🏆 {ctx.author.mention} vừa mở khóa thành tựu mới: **{ach['name']}**! (+{ach['reward_coin']:,} coin, +{ach['reward_xp']} XP)", delete_after=30)

        await db.update_bid(auction['message_id'], amount, ctx.author.id)

        try:
            auction_msg = await ctx.channel.fetch_message(auction['message_id'])
            original_embed = auction_msg.embeds[0]
            original_embed.set_field_at(
                1, name="📈 Giá hiện tại", value=f"**{amount:,}** coin", inline=True)
            original_embed.set_field_at(
                2, name="👑 Người giữ giá", value=ctx.author.mention, inline=False)
            await auction_msg.edit(embed=original_embed)
        except (discord.NotFound, discord.HTTPException):
            pass

        await ctx.send(f"✅ {ctx.author.mention} đã trả giá thành công!", delete_after=5, ephemeral=True)

    # cogs/auction.py

    @tasks.loop(minutes=1)
    async def check_finished_auctions(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        active_auctions = await db.get_active_auctions()
        for auction in active_auctions:
            end_time = datetime.datetime.fromisoformat(
                auction['end_timestamp'])
            if now < end_time:
                continue

            await db.end_auction(auction['message_id'])

            guild = self.bot.get_guild(auction['guild_id'])
            if not guild:
                continue
            # 'channel' ở đây chính là kênh đấu giá gốc
            channel = guild.get_channel(auction['channel_id'])
            if not channel:
                continue

            winner_id, final_price = auction.get(
                'highest_bidder_id'), auction['current_bid']
            item_name_display = auction['item_name']

            if winner_id:
                try:
                    winner = await guild.fetch_member(winner_id)
                    seller = await guild.fetch_member(auction['seller_id'])
                except discord.NotFound:
                    await db.update_coins(winner_id, guild.id, final_price)
                    await channel.send(f"⚠️ Phiên đấu giá cho **{auction['item_name']}** đã kết thúc nhưng người thắng/người bán không còn trong server. Giao dịch đã được hoàn lại.")
                    continue

                if seller:
                    await db.update_coins(seller.id, guild.id, final_price)

                if auction['item_type'] == 'ROLE':
                    if role_to_award := guild.get_role(auction['item_id']):
                        try:
                            await winner.add_roles(role_to_award, reason=f"Thắng đấu giá vật phẩm {item_name_display}")
                            item_name_display = role_to_award.mention
                        except discord.Forbidden:
                            await channel.send(f"⚠️ Bot không có quyền để trao role **{role_to_award.name}** cho người thắng cuộc.")

                # --- PHẦN THÔNG BÁO (ĐÃ CẬP NHẬT ĐỂ GỬI TẠI KÊNH GỐC) ---
                result_embed = discord.Embed(
                    title="🔨 KẾT THÚC PHIÊN ĐẤU GIÁ 🔨",
                    description=f"Một vật phẩm đã tìm thấy chủ nhân mới!",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                result_embed.add_field(
                    name="✨ Người Chiến Thắng", value=f"**{winner.mention}**", inline=True)
                result_embed.add_field(
                    name="🏆 Vật Phẩm", value=f"**{item_name_display}**", inline=True)
                result_embed.add_field(
                    name="💰 Giá Cuối Cùng", value=f"### {final_price:,} coin", inline=False)
                result_embed.set_thumbnail(url=winner.display_avatar.url)
                result_embed.set_footer(
                    text=f"Người bán: {seller.display_name}", icon_url=seller.display_avatar.url)

                # Gửi thông báo trực tiếp vào kênh 'channel' (kênh đấu giá)
                await channel.send(embed=result_embed)

                try:
                    await winner.send(f"Chúc mừng! Bạn đã thắng đấu giá và nhận được **{item_name_display}** với giá **{final_price:,}** coin tại server **{guild.name}**.")
                except discord.Forbidden:
                    pass
            else:
                await channel.send(f"⚠️ Phiên đấu giá cho **{auction['item_name']}** đã kết thúc mà không có ai tham gia.")

            try:
                auction_msg = await channel.fetch_message(auction['message_id'])
                original_embed = auction_msg.embeds[0]
                original_embed.title = f"[ĐÃ KẾT THÚC] PHIÊN ĐẤU GIÁ"
                original_embed.color = discord.Color.dark_grey()
                original_embed.set_thumbnail(url=None)
                # Chỉnh sửa tin nhắn gốc và xóa các nút bấm
                await auction_msg.edit(embed=original_embed, view=None)
            except (discord.NotFound, discord.HTTPException):
                pass

    @check_finished_auctions.before_loop
    async def before_check_auctions(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Auction(bot))
