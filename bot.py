import os
import re
import calendar
import logging
import threading
from datetime import datetime, date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y"]

# ============================================================
# Health server
# ============================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
        self.wfile.write(b"Date Bot alive.")
    def do_HEAD(self):
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# ============================================================
# Date logic
# ============================================================
def parse_date(s: str) -> date:
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Couldn't parse `{s}`. Use YYYY-MM-DD (e.g. `1990-05-15`)")

def calc_age(birthday: date):
    today = date.today()
    years = today.year - birthday.year
    months = today.month - birthday.month
    days = today.day - birthday.day
    if days < 0:
        months -= 1
        prev_month = today.month - 1 or 12
        prev_year = today.year if today.month > 1 else today.year - 1
        days += calendar.monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12
    return years, months, days, (today - birthday).days

def next_birthday(birthday: date):
    today = date.today()
    try:
        this = date(today.year, birthday.month, birthday.day)
    except ValueError:  # Feb 29 in non-leap year
        this = date(today.year, 3, 1)
    if this < today:
        try:
            nxt = date(today.year + 1, birthday.month, birthday.day)
        except ValueError:
            nxt = date(today.year + 1, 3, 1)
    else:
        nxt = this
    return nxt, (nxt - today).days

# ============================================================
# Menus
# ============================================================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎂 Age Calculator", callback_data="age")],
        [InlineKeyboardButton("📅 Days Between Dates", callback_data="between")],
        [InlineKeyboardButton("⏰ Countdown to Date", callback_data="countdown")],
        [InlineKeyboardButton("➕ Add/Subtract Days", callback_data="addsub")],
        [InlineKeyboardButton("📆 Day of the Week", callback_data="dow")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]])

# ============================================================
# Handlers
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📅 *Date Calculator*\n\n"
        "Calculate age, days between dates, countdowns, and more.\n\n"
        "Pick a tool:",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cb = query.data

    if cb == "home":
        context.user_data.clear()
        await query.edit_message_text(
            "📅 *Date Calculator*\n\nPick a tool:",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        return

    if cb == "age":
        context.user_data["mode"] = "age"
        await query.edit_message_text(
            "🎂 *Age Calculator*\n\n"
            "Send your birthday in any format:\n"
            "`1990-05-15`  •  `15/05/1990`  •  `15-05-1990`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "between":
        context.user_data["mode"] = "between_first"
        await query.edit_message_text(
            "📅 *Days Between Dates*\n\n"
            "Step 1 of 2: Send the FIRST date.\n\n"
            "Format: `YYYY-MM-DD` (e.g. `2026-01-01`)",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "countdown":
        context.user_data["mode"] = "countdown"
        await query.edit_message_text(
            "⏰ *Countdown to Date*\n\n"
            "Send the target date and I'll tell you how many days until then.\n\n"
            "Example: `2026-12-25`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "addsub":
        context.user_data["mode"] = "addsub_date"
        await query.edit_message_text(
            "➕ *Add/Subtract Days*\n\n"
            "Step 1 of 2: Send the starting date.\n\n"
            "Format: `YYYY-MM-DD`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "dow":
        context.user_data["mode"] = "dow"
        await query.edit_message_text(
            "📆 *Day of the Week*\n\n"
            "Send a date and I'll tell you what day of the week it is.\n\n"
            "Example: `2026-12-25`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if cb == "help":
        await query.edit_message_text(
            "ℹ️ *How to use*\n\n"
            "Date formats accepted:\n"
            "• `YYYY-MM-DD` → `2026-12-25`\n"
            "• `DD/MM/YYYY` → `25/12/2026`\n"
            "• `DD-MM-YYYY` → `25-12-2026`\n"
            "• `DD.MM.YYYY` → `25.12.2026`\n\n"
            "All calculations are local — no internet needed.",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()

    # AGE
    if mode == "age":
        try:
            bday = parse_date(text)
        except ValueError as e:
            await update.message.reply_text(f"⚠️ {e}", parse_mode="Markdown")
            return
        if bday > date.today():
            await update.message.reply_text("⚠️ That's in the future. Send your past birthday.")
            return
        years, months, days, total = calc_age(bday)
        nxt, days_until = next_birthday(bday)
        await update.message.reply_text(
            f"🎂 *Your Age*\n\n"
            f"Born: `{bday.strftime('%A, %d %B %Y')}`\n\n"
            f"You are *{years} years, {months} months, {days} days* old.\n\n"
            f"That's *{total:,} days* total.\n\n"
            f"🎉 Next birthday: `{nxt.strftime('%A, %d %B %Y')}` ({days_until} days away)",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.pop("mode", None)
        return

    # BETWEEN: step 1
    if mode == "between_first":
        try:
            d1 = parse_date(text)
        except ValueError as e:
            await update.message.reply_text(f"⚠️ {e}", parse_mode="Markdown")
            return
        context.user_data["d1"] = d1.isoformat()
        context.user_data["mode"] = "between_second"
        await update.message.reply_text(
            f"✅ First date: `{d1.strftime('%A, %d %B %Y')}`\n\n"
            "Step 2 of 2: Send the SECOND date.",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    # BETWEEN: step 2
    if mode == "between_second":
        try:
            d2 = parse_date(text)
        except ValueError as e:
            await update.message.reply_text(f"⚠️ {e}", parse_mode="Markdown")
            return
        d1 = date.fromisoformat(context.user_data.get("d1"))
        days = abs((d2 - d1).days)
        first, second = (d1, d2) if d1 <= d2 else (d2, d1)
        await update.message.reply_text(
            f"📅 *Days Between*\n\n"
            f"From: `{first.strftime('%a, %d %b %Y')}`\n"
            f"To: `{second.strftime('%a, %d %b %Y')}`\n\n"
            f"⏱ *{days:,} days*\n"
            f"   ≈ {days/7:,.1f} weeks\n"
            f"   ≈ {days/30.44:,.1f} months\n"
            f"   ≈ {days/365.25:,.2f} years",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.clear()
        return

    # COUNTDOWN
    if mode == "countdown":
        try:
            target = parse_date(text)
        except ValueError as e:
            await update.message.reply_text(f"⚠️ {e}", parse_mode="Markdown")
            return
        diff = (target - date.today()).days
        if diff > 0:
            await update.message.reply_text(
                f"⏰ *Countdown*\n\n"
                f"Date: `{target.strftime('%A, %d %B %Y')}`\n\n"
                f"*{diff:,} days* until that date.",
                reply_markup=main_menu(),
                parse_mode="Markdown",
            )
        elif diff < 0:
            await update.message.reply_text(
                f"📜 *Looking back*\n\n"
                f"Date: `{target.strftime('%A, %d %B %Y')}`\n\n"
                f"*{-diff:,} days* since that date.",
                reply_markup=main_menu(),
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"🎉 That's TODAY! ({target.strftime('%A, %d %B %Y')})",
                reply_markup=main_menu(),
            )
        context.user_data.pop("mode", None)
        return

    # ADD/SUB: step 1
    if mode == "addsub_date":
        try:
            d = parse_date(text)
        except ValueError as e:
            await update.message.reply_text(f"⚠️ {e}", parse_mode="Markdown")
            return
        context.user_data["addsub_date"] = d.isoformat()
        context.user_data["mode"] = "addsub_days"
        await update.message.reply_text(
            f"✅ Start: `{d.strftime('%A, %d %B %Y')}`\n\n"
            "Step 2 of 2: How many days to add or subtract?\n\n"
            "Examples: `+30`, `-7`, `90`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    # ADD/SUB: step 2
    if mode == "addsub_days":
        m = re.match(r"^([+-]?\d+)$", text.replace(" ", ""))
        if not m:
            await update.message.reply_text("⚠️ Send a number like `30`, `+30`, or `-7`.", parse_mode="Markdown")
            return
        offset = int(m.group(1))
        d = date.fromisoformat(context.user_data.get("addsub_date"))
        result = d + timedelta(days=offset)
        direction = "after" if offset >= 0 else "before"
        await update.message.reply_text(
            f"➕ *Date Math*\n\n"
            f"Start: `{d.strftime('%A, %d %B %Y')}`\n"
            f"Offset: {offset:+d} days\n\n"
            f"Result: `{result.strftime('%A, %d %B %Y')}`\n"
            f"_({abs(offset)} days {direction})_",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.clear()
        return

    # DAY OF WEEK
    if mode == "dow":
        try:
            d = parse_date(text)
        except ValueError as e:
            await update.message.reply_text(f"⚠️ {e}", parse_mode="Markdown")
            return
        await update.message.reply_text(
            f"📆 *Day of the Week*\n\n"
            f"`{d.strftime('%d %B %Y')}` is a *{DAYS[d.weekday()]}*",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.pop("mode", None)
        return

    await update.message.reply_text(
        "Tap a button to use a tool. /start",
        reply_markup=main_menu(),
    )

# ============================================================
# Main
# ============================================================
def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        log.critical("BOT_TOKEN env var missing!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Date Calculator Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
