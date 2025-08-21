# cogs/moderation.py
import discord
from discord.ext import commands
import datetime
import re
import database as db
import asyncio
from .utils import checks
from discord import app_commands

# --- LỚP VIEW XÁC NHẬN ---


class ConfirmationView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=60.0)
        self.author = author
        self.confirmed = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Đây không phải là yêu cầu của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Xác nhận", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="❌ Hủy", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


def parse_duration_mod(duration_str: str) -> (datetime.timedelta, str):
    match = re.match(r"(\d+)([mhd])", duration_str.lower())
    if not match:
        raise ValueError(
            "Định dạng thời gian không hợp lệ. Ví dụ: `10m`, `2h`, `7d`.")
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        return (datetime.timedelta(minutes=value), f"{value} phút")
    if unit == 'h':
        return (datetime.timedelta(hours=value), f"{value} giờ")
    if unit == 'd':
        return (datetime.timedelta(days=value), f"{value} ngày")


class Moderation(commands.Cog):
    """🛠️ Lệnh dành cho Quản trị viên và Điều hành viên"""
    COG_EMOJI = "🛠️"

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='clear', description="Xóa nhanh một số lượng tin nhắn trong kênh.")
    @checks.has_permissions(manage_messages=True)
    @app_commands.rename(amount="số_lượng")
    async def clear(self, ctx: commands.Context, amount: int):
        if amount <= 0:
            return await ctx.send("Số lượng phải lớn hơn 0.", delete_after=5, ephemeral=True)
        if amount > 100:
            return await ctx.send("Bạn chỉ có thể xóa tối đa 100 tin nhắn mỗi lần.", delete_after=5, ephemeral=True)

        # <<< SỬA LỖI TẠI ĐÂY >>>
        if ctx.interaction:
            # Gọi defer và followup từ ctx.interaction
            await ctx.interaction.response.defer(ephemeral=True)
            deleted = await ctx.channel.purge(limit=amount)
            await ctx.interaction.followup.send(f'✅ Đã xóa **{len(deleted)}** tin nhắn.', ephemeral=True)
        else:  # Lệnh prefix hoạt động như cũ
            view = ConfirmationView(ctx.author)
            confirmation_msg = await ctx.send(f"Bạn có chắc muốn xóa **{amount}** tin nhắn không?", view=view, delete_after=60)
            await view.wait()
            if view.confirmed is True:
                await confirmation_msg.delete()
                deleted = await ctx.channel.purge(limit=amount)
                await ctx.send(f'✅ Đã xóa **{len(deleted)}** tin nhắn.', delete_after=5)
            elif view.confirmed is False:
                await confirmation_msg.edit(content="Đã hủy thao tác.", view=None, delete_after=5)
            else:
                try:
                    for item in view.children:
                        item.disabled = True
                    await confirmation_msg.edit(content="Yêu cầu đã hết hạn.", view=view, delete_after=5)
                except discord.NotFound:
                    pass

    @commands.hybrid_command(name='clearwarns', description="Xóa hết cảnh cáo của một thành viên.")
    @checks.has_permissions(kick_members=True)
    @app_commands.rename(member="thành_viên")
    async def clearwarns(self, ctx: commands.Context, member: discord.Member):
        warnings_list = await db.get_warnings(member.id, ctx.guild.id)
        if not warnings_list:
            return await ctx.send(f"{member.display_name} không có cảnh cáo nào.", delete_after=10, ephemeral=True)

        view = ConfirmationView(ctx.author)
        confirmation_msg = await ctx.send(f"Bạn có chắc muốn xóa **{len(warnings_list)}** cảnh cáo của {member.mention} không?", view=view)

        await view.wait()
        if view.confirmed is True:
            count = await db.clear_warnings(member.id, ctx.guild.id)
            await confirmation_msg.edit(content=f"✅ Đã xóa thành công **{count}** cảnh cáo của {member.mention}.", view=None, embed=None, delete_after=10)
        elif view.confirmed is False:
            await confirmation_msg.edit(content="Đã hủy thao tác.", view=None, delete_after=5)
        else:
            try:
                await confirmation_msg.edit(view=None)
            except discord.NotFound:
                pass

    @commands.hybrid_command(name='kick', description="Đuổi một thành viên khỏi server.")
    @checks.has_permissions(kick_members=True)
    @app_commands.rename(member="thành_viên", reason="lý_do")
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Không có lý do."):
        if member == ctx.author or (ctx.author.top_role <= member.top_role and ctx.guild.owner != ctx.author):
            return await ctx.send("Bạn không có quyền kick người này.", ephemeral=True)
        if ctx.guild.me.top_role <= member.top_role:
            return await ctx.send("Bot không có quyền kick người này do vai trò của họ cao hơn hoặc bằng bot.", ephemeral=True)

        embed = discord.Embed(title="👢 Đuổi thành viên",
                              description=f"Đã đuổi {member.mention}.", color=0xDD2E44, timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name="Lý do", value=reason)
        embed.set_footer(text=f"Thực hiện bởi {ctx.author.display_name}")
        await member.kick(reason=f"{reason} (Bởi {ctx.author})")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='ban', description="Cấm một thành viên khỏi server.")
    @checks.has_permissions(ban_members=True)
    @app_commands.rename(member="thành_viên", reason="lý_do")
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Không có lý do."):
        if member == ctx.author or (ctx.author.top_role <= member.top_role and ctx.guild.owner != ctx.author):
            return await ctx.send("Bạn không có quyền cấm người này.", ephemeral=True)
        if ctx.guild.me.top_role <= member.top_role:
            return await ctx.send("Bot không có quyền cấm người này do vai trò của họ cao hơn hoặc bằng bot.", ephemeral=True)

        embed = discord.Embed(
            title="🔨 Cấm thành viên", description=f"Đã cấm {member.mention}.", color=0x000000, timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name="Lý do", value=reason)
        embed.set_footer(text=f"Thực hiện bởi {ctx.author.display_name}")
        await member.ban(reason=f"{reason} (Bởi {ctx.author})")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='unban', description="Gỡ cấm cho một người dùng bằng ID của họ.")
    @checks.has_permissions(ban_members=True)
    @app_commands.rename(user_id="id_người_dùng", reason="lý_do")
    async def unban(self, ctx: commands.Context, user_id: str, *, reason: str = "Gỡ cấm bởi quản trị viên."):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user, reason=reason)
            await ctx.send(embed=discord.Embed(title="♻️ Gỡ cấm thành công", description=f"Đã gỡ cấm cho **{user.name}** (`{user.id}`).", color=discord.Color.green()))
        except (ValueError, discord.NotFound):
            await ctx.send(f'Không tìm thấy người dùng với ID `{user_id}` trong danh sách cấm.', ephemeral=True)

    @commands.hybrid_command(name='restrict', description="Cấm chat một thành viên trong một khoảng thời gian.")
    @checks.has_permissions(manage_roles=True)
    @app_commands.rename(member="thành_viên", time_str="thời_gian", reason="lý_do")
    async def restrict(self, ctx: commands.Context, member: discord.Member, time_str: str, *, reason: str = "Không có lý do."):
        config = await db.get_or_create_config(ctx.guild.id)
        muted_role_id = config.get('muted_role_id')
        if not muted_role_id:
            return await ctx.send("⚠️ Role cấm chat chưa được thiết lập. Dùng `/set mutedrole`.", delete_after=10, ephemeral=True)
        muted_role = ctx.guild.get_role(muted_role_id)
        if not muted_role:
            return await ctx.send(f"⚠️ Role cấm chat (ID: {muted_role_id}) không còn tồn tại.", delete_after=10, ephemeral=True)
        if muted_role in member.roles:
            return await ctx.send(f"ℹ️ {member.mention} đã bị cấm chat từ trước.", delete_after=10, ephemeral=True)

        try:
            duration_delta, duration_text = parse_duration_mod(time_str)
        except ValueError as e:
            return await ctx.send(f"❌ {e}", delete_after=10, ephemeral=True)

        try:
            await member.add_roles(muted_role, reason=f"{reason} (Bởi {ctx.author})")
            expiry = datetime.datetime.now(
                datetime.timezone.utc) + duration_delta
            await db.add_temporary_role(member.id, ctx.guild.id, muted_role.id, expiry.isoformat())

            embed = discord.Embed(
                title="🚫 Hạn chế thành viên", color=discord.Color.red())
            embed.description = f"Đã cấm chat {member.mention}."
            embed.add_field(name="Thời gian", value=f"**{duration_text}**")
            embed.add_field(name="Lý do", value=reason, inline=False)
            embed.set_footer(text=f"Thực hiện bởi {ctx.author.display_name}")
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("Bot không có quyền để thêm role cấm chat cho thành viên này.", delete_after=10, ephemeral=True)

    @commands.hybrid_command(name='unrestrict', description="Gỡ cấm chat cho một thành viên.")
    @checks.has_permissions(manage_roles=True)
    @app_commands.rename(member="thành_viên", reason="lý_do")
    async def unrestrict(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Gỡ hạn chế bởi quản trị viên."):
        config = await db.get_or_create_config(ctx.guild.id)
        muted_role_id = config.get('muted_role_id')
        if not muted_role_id:
            return await ctx.send("⚠️ Role cấm chat chưa được thiết lập.", delete_after=10, ephemeral=True)
        muted_role = ctx.guild.get_role(muted_role_id)
        if not muted_role or muted_role not in member.roles:
            return await ctx.send(f"ℹ️ {member.mention} hiện không bị cấm chat.", delete_after=10, ephemeral=True)

        try:
            await member.remove_roles(muted_role, reason=f"{reason} (Bởi {ctx.author})")
            await db.remove_temporary_role(member.id, ctx.guild.id, muted_role.id)
            embed = discord.Embed(
                title="✅ Gỡ bỏ hạn chế", description=f"Đã gỡ cấm chat cho {member.mention}.", color=discord.Color.green())
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("Bot không có quyền để gỡ role cấm chat khỏi thành viên này.", delete_after=10, ephemeral=True)

    @commands.hybrid_command(name='warn', description="Cảnh cáo một thành viên.")
    @checks.has_permissions(kick_members=True)
    @app_commands.rename(member="thành_viên", reason="lý_do")
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Không có lý do."):
        if member == ctx.author or (ctx.author.top_role <= member.top_role and ctx.guild.owner != ctx.author):
            return await ctx.send("Bạn không thể cảnh cáo người này.", ephemeral=True)

        await db.add_warning(member.id, ctx.guild.id, ctx.author.id, reason)
        embed = discord.Embed(title="⚠️ Đã cảnh cáo thành viên", color=discord.Color.orange(
        ), timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name="Thành viên", value=member.mention, inline=True)
        embed.add_field(name="Người thực hiện",
                        value=ctx.author.mention, inline=True)
        embed.add_field(name="Lý do", value=reason, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)
        try:
            await member.send(f"Bạn đã nhận một cảnh cáo tại server **{ctx.guild.name}**. Lý do: {reason}")
        except discord.Forbidden:
            pass

    @commands.hybrid_command(name='warnings', description="Xem lịch sử cảnh cáo của một thành viên.")
    @checks.has_permissions(kick_members=True)
    @app_commands.rename(member="thành_viên")
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        warnings_list = await db.get_warnings(member.id, ctx.guild.id)
        embed = discord.Embed(
            title=f"Lịch sử cảnh cáo của {member.display_name}", color=discord.Color.orange())
        embed.set_thumbnail(url=member.display_avatar.url)

        if not warnings_list:
            embed.description = "Người dùng này không có cảnh cáo nào."
        else:
            description = ""
            for i, warn_data in enumerate(warnings_list):
                mod = ctx.guild.get_member(
                    warn_data['moderator_id']) or f"ID: {warn_data['moderator_id']}"
                ts = int(datetime.datetime.fromisoformat(
                    warn_data['timestamp']).timestamp())
                description += f"**#{i+1}** | <t:{ts}:R> bởi {mod.mention if isinstance(mod, discord.Member) else mod}\n> **Lý do:** {warn_data['reason']}\n"
            embed.description = description

        await ctx.send(embed=embed)

    @commands.hybrid_group(name="set", description="Các lệnh cấu hình cho server (Admin).")
    async def _set(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @_set.command(name="welcome", description="Đặt kênh chào mừng thành viên mới.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(channel="kênh")
    async def set_welcome(self, ctx: commands.Context, channel: discord.TextChannel):
        await db.update_config(ctx.guild.id, 'welcome_channel_id', channel.id)
        await ctx.send(f"✅ Đã đặt kênh chào mừng là {channel.mention}.", ephemeral=True)

    @_set.command(name="goodbye", description="Đặt kênh thông báo thành viên rời đi.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(channel="kênh")
    async def set_goodbye(self, ctx: commands.Context, channel: discord.TextChannel):
        await db.update_config(ctx.guild.id, 'goodbye_channel_id', channel.id)
        await ctx.send(f"✅ Đã đặt kênh tạm biệt là {channel.mention}.", ephemeral=True)

    @_set.command(name="announcement", description="Đặt kênh thông báo chung (lên cấp, trúng thưởng...).")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(channel="kênh")
    async def set_announcement(self, ctx: commands.Context, channel: discord.TextChannel):
        await db.update_config(ctx.guild.id, 'announcement_channel_id', channel.id)
        await ctx.send(f"✅ Đã đặt kênh thông báo là {channel.mention}.", ephemeral=True)

    @_set.command(name="commandchannel", description="Đặt kênh riêng cho lệnh (sẽ không nhận XP/coin khi chat).")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(channel="kênh")
    async def set_commandchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await db.update_config(ctx.guild.id, 'command_channel_id', channel.id)
        await ctx.send(f"✅ Đã đặt kênh lệnh là {channel.mention}. XP và Coin sẽ không được tính ở đây.", ephemeral=True)

    @_set.command(name="mutedrole", description="Đặt role để cấm chat thành viên.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(role="role")
    async def set_mutedrole(self, ctx: commands.Context, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(f"❌ Bot không thể quản lý role {role.mention}. Vui lòng kéo role của bot lên trên.", ephemeral=True)
        await db.update_config(ctx.guild.id, 'muted_role_id', role.id)
        await ctx.send(f"✅ Đã đặt role cấm chat là {role.mention}. Hãy đảm bảo bạn đã cấu hình quyền cho role này!", ephemeral=True)

    @_set.command(name="luckrole", description="Đặt role may mắn (tăng tỉ lệ nhận thưởng).")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(role="role")
    async def set_luckrole(self, ctx: commands.Context, role: discord.Role):
        await db.update_config(ctx.guild.id, 'luck_role_id', role.id)
        await ctx.send(f"✅ Đã đặt **{role.mention}** làm role 'Thiên Mệnh Chi Tử'.", ephemeral=True)

    @_set.command(name="toprole", description="Đặt role thưởng cho top 1 leaderboard hàng tuần.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(role="role")
    async def set_toprole(self, ctx: commands.Context, role: discord.Role):
        await db.update_config(ctx.guild.id, 'top_role_id', role.id)
        await ctx.send(f"✅ Đã đặt **{role.mention}** làm role thưởng cho Top 1 hàng tuần.", ephemeral=True)

    @_set.command(name="viprole", description="Đặt role VIP nhận boost kinh tế.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(role="role")
    async def set_viprole(self, ctx: commands.Context, role: discord.Role):
        await db.update_config(ctx.guild.id, 'vip_role_id', role.id)
        await ctx.send(f"✅ Đã đặt **{role.mention}** làm role VIP.", ephemeral=True)

    @_set.command(name="debtorrole", description="Đặt role cho người chơi vỡ nợ.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(role="role")
    async def set_debtorrole(self, ctx: commands.Context, role: discord.Role):
        await db.update_config(ctx.guild.id, 'debtor_role_id', role.id)
        await ctx.send(f"✅ Đã đặt **{role.mention}** làm role Vỡ Nợ.", ephemeral=True)

    @_set.command(name="rainbowrole", description="Đặt role sẽ được dùng cho hiệu ứng tên cầu vồng.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(role="role")
    async def set_rainbowrole(self, ctx: commands.Context, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send(f"❌ Bot không thể quản lý role {role.mention}. Vui lòng kéo role của bot lên trên.", ephemeral=True)
        await db.update_config(ctx.guild.id, 'rainbow_role_id', role.id)
        await ctx.send(f"✅ Đã đặt **{role.mention}** làm role Cầu Vồng.", ephemeral=True)

    @commands.hybrid_group(name="eco", description="Các lệnh quản lý kinh tế của thành viên (Admin).")
    async def eco(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @eco.command(name="set", description="Đặt số coin của một thành viên thành giá trị cụ thể.")
    @checks.is_administrator()
    @app_commands.rename(member="thành_viên", amount="số_tiền")
    async def eco_set(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount < 0:
            return await ctx.send("Số tiền không thể là số âm.", ephemeral=True)
        await db.set_coins(member.id, ctx.guild.id, amount)
        embed = discord.Embed(
            description=f"✅ Đã đặt số dư của {member.mention} thành **{amount:,}** coin.", color=discord.Color.green())
        await ctx.send(embed=embed)

    @eco.command(name="add", description="Cộng thêm coin vào tài khoản của thành viên.")
    @checks.is_administrator()
    @app_commands.rename(member="thành_viên", amount="số_tiền")
    async def eco_add(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            return await ctx.send("Số tiền cần cộng phải lớn hơn 0.", ephemeral=True)
        await db.update_coins(member.id, ctx.guild.id, amount)
        new_balance_data = await db.get_or_create_user(member.id, ctx.guild.id)
        embed = discord.Embed(
            description=f"✅ Đã cộng **{amount:,}** coin cho {member.mention}.\nSố dư mới: **{new_balance_data['coins']:,}** coin.", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @eco.command(name="remove", aliases=['sub'], description="Trừ bớt coin khỏi tài khoản của thành viên.")
    @checks.is_administrator()
    @app_commands.rename(member="thành_viên", amount="số_tiền")
    async def eco_remove(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            return await ctx.send("Số tiền cần trừ phải lớn hơn 0.", ephemeral=True)
        await db.update_coins(member.id, ctx.guild.id, -amount)
        new_balance_data = await db.get_or_create_user(member.id, ctx.guild.id)
        embed = discord.Embed(
            description=f"✅ Đã trừ **{amount:,}** coin từ {member.mention}.\nSố dư mới: **{new_balance_data['coins']:,}** coin.", color=discord.Color.red())
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="invadmin", description="Các lệnh quản lý kho đồ của thành viên (Admin).")
    async def invadmin(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    # cogs/moderation.py -> class Moderation

    @invadmin.command(name="add", description="Thêm vật phẩm vào kho đồ của thành viên.")
    @checks.is_administrator()
    @app_commands.rename(member="thành_viên", item_id="id_vật_phẩm", quantity="số_lượng")
    async def invadmin_add(self, ctx: commands.Context, member: discord.Member, item_id: str, quantity: int = 1):
        # Lấy danh sách item hợp lệ từ file economy
        try:
            # <<< SỬA LỖI TẠI ĐÂY: Đổi từ '..cogs.economy' thành '.economy' >>>
            from .economy import SHOP_ITEMS
        except (ImportError, SystemError):
            await ctx.send("❌ Lỗi: Không thể tải danh sách vật phẩm.", ephemeral=True)
            return

        if item_id not in SHOP_ITEMS:
            valid_ids = ", ".join([f"`{k}`" for k in SHOP_ITEMS.keys()])
            return await ctx.send(f"❌ ID vật phẩm không hợp lệ. Các ID có sẵn: {valid_ids}", ephemeral=True)

        if quantity <= 0:
            return await ctx.send("Số lượng phải lớn hơn 0.", ephemeral=True)

        await db.add_item_to_inventory(member.id, ctx.guild.id, item_id, quantity)

        # Xử lý đặc biệt cho vé xổ số
        if item_id == 'lottery_ticket':
            await db.add_lottery_tickets(ctx.guild.id, member.id, quantity)

        embed = discord.Embed(
            description=f"✅ Đã thêm thành công **x{quantity}** vật phẩm `{item_id}` ({SHOP_ITEMS[item_id]['name']}) vào kho đồ của {member.mention}.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @invadmin.command(name="remove", description="Xóa một vật phẩm khỏi kho đồ của thành viên.")
    @checks.is_administrator()
    @app_commands.rename(member="thành_viên", item_id="id_vật_phẩm", quantity="số_lượng")
    async def invadmin_remove(self, ctx: commands.Context, member: discord.Member, item_id: str, quantity: int = 1):
        if quantity <= 0:
            return await ctx.send("Số lượng phải lớn hơn 0.", ephemeral=True)

        success = await db.remove_item_from_inventory(member.id, ctx.guild.id, item_id, quantity)
        if success:
            embed = discord.Embed(
                description=f"✅ Đã xóa thành công **x{quantity}** vật phẩm `{item_id}` khỏi kho đồ của {member.mention}.", color=discord.Color.green())
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                description=f"❌ Thao tác thất bại. {member.mention} không có đủ **x{quantity}** vật phẩm `{item_id}`.", color=discord.Color.red())
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="testcolor", description="(Chủ Bot) Lệnh debug để kiểm tra chức năng đổi màu role.", hidden=True)
    @commands.is_owner()
    async def test_color(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        config = await db.get_or_create_config(ctx.guild.id)
        rainbow_role_id = config.get('rainbow_role_id')
        if not rainbow_role_id:
            return await ctx.followup.send("❌ Lỗi: Role cầu vồng chưa được set trên server này.", ephemeral=True)

        role = ctx.guild.get_role(rainbow_role_id)
        if not role:
            return await ctx.followup.send(f"❌ Lỗi: Không tìm thấy role với ID {rainbow_role_id}.", ephemeral=True)

        test_color = discord.Color.random()
        try:
            await role.edit(color=test_color, reason="Test color command")
            await ctx.followup.send(f"✅ THÀNH CÔNG! Role đã được đổi màu sang `{test_color}`.", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("❌ THẤT BẠI: Bot thiếu quyền (FORBIDDEN).", ephemeral=True)
        except Exception as e:
            await ctx.followup.send(f"❌ THẤT BẠI: Lỗi không xác định: `{e}`", ephemeral=True)

    @commands.hybrid_command(name="setup_tutien_roles", description="(Admin) Tự động tạo các role Tu Tiên cấp cao.", hidden=True)
    @checks.has_permissions(manage_roles=True)
    async def setup_tutien_roles(self, ctx: commands.Context):
        await ctx.defer()
        roles_to_create = [
            {'level': 540, 'emoji': '⚜️',
                'name': 'Thiên Đạo Chi Chủ', 'color': '#C3B1E1'},
            {'level': 580, 'emoji': '⚖️',
                'name': 'Pháp Tắc Chí Tôn', 'color': '#D9ABDE'},
            {'level': 620, 'emoji': '🪐',
                'name': 'Vạn Giới Thần Chủ', 'color': '#A0D6B4'},
            {'level': 660, 'emoji': '♾️',
                'name': 'Vô Cực Thánh Nhân', 'color': '#F8C8DC'},
            {'level': 710, 'emoji': '🌪️',
                'name': 'Hỗn Độn Cổ Thần', 'color': '#B5A6A5'},
            {'level': 760, 'emoji': '☸️',
                'name': 'Luân Hồi Chúa Tể', 'color': '#E3735E'},
            {'level': 820, 'emoji': '⚫',
                'name': 'Hư Vô Cảnh Giới', 'color': '#B2C2D2'},
            {'level': 880, 'emoji': '👑',
                'name': 'Nguyên Sơ Chúa Tể', 'color': '#EAE6E1'},
            {'level': 940, 'emoji': '✨',
                'name': 'Đại Đạo Hóa Thân', 'color': '#F4E99B'},
            {'level': 999, 'emoji': '💠',
                'name': 'Thiên Cổ Chúa Tể', 'color': '#F7F5F0'},
        ]

        existing_roles = [role.name for role in ctx.guild.roles]
        created_count, skipped_count = 0, 0

        status_msg = await ctx.followup.send("⏳ Bắt đầu quá trình tạo role Tu Tiên cấp cao...")

        for role_data in roles_to_create:
            full_name = f"{role_data['emoji']} {role_data['name']}"
            if full_name in existing_roles:
                skipped_count += 1
                continue

            try:
                hex_color = role_data['color'].replace('#', '')
                color_obj = discord.Color(int(hex_color, 16))
                await ctx.guild.create_role(name=full_name, color=color_obj, reason="Tự động thiết lập hệ thống role Tu Tiên")
                await status_msg.edit(content=f"⏳ Đã tạo thành công role: **{full_name}**")
                created_count += 1
                await asyncio.sleep(1)
            except discord.Forbidden:
                await status_msg.edit(content=f"❌ **LỖI:** Bot không có quyền `Manage Roles`.")
                return
            except Exception as e:
                await ctx.channel.send(f"⚠️ Gặp lỗi khi tạo role '{full_name}': {e}")

        final_message = f"🎉 **Hoàn tất!**\n✅ Đã tạo mới: **{created_count}** role.\nℹ️ Bỏ qua (đã tồn tại): **{skipped_count}** role."
        await status_msg.edit(content=final_message)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
