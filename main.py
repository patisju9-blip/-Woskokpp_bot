import json
import logging
import os
import uuid

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, Update,
)
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "9297948785:AAHdF9Pbb04T-P-sxNsfdePq2nV6Mhxi-nY"
STORE_NAME = "My Store"
PAYMENT_INFO = "ABA: 000 000 000\nName: Your Name"

CATALOG = {
    "c1": {
        "name": "Category 1",
        "desc": "Write your product description here.",
        "photo": None,
        "plans": {
            "p1": {"name": "1 Hour", "price": 0.40},
            "p2": {"name": "3 Hours", "price": 0.70},
            "p3": {"name": "1 Day", "price": 2.00},
        },
    },
    "c2": {
        "name": "Category 2",
        "desc": "Write your product description here.",
        "photo": None,
        "plans": {
            "p1": {"name": "1 Day", "price": 1.50},
            "p2": {"name": "7 Days", "price": 8.00},
        },
    },
}

STOCK_FILE = "stock.json"
ADMIN_FILE = "admin.json"
ORDERS = {}


def get_admin():
    if os.path.exists(ADMIN_FILE):
        with open(ADMIN_FILE, encoding="utf-8") as f:
            return json.load(f).get("id")
    return None


def load_stock():
    if os.path.exists(STOCK_FILE):
        with open(STOCK_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_stock(stock):
    with open(STOCK_FILE, "w", encoding="utf-8") as f:
        json.dump(stock, f, indent=2)


def stock_of(cid, pid):
    return len(load_stock().get(f"{cid}:{pid}", []))


def categories_markup():
    rows = [[InlineKeyboardButton(c["name"], callback_data=f"cat:{cid}")]
            for cid, c in CATALOG.items()]
    return InlineKeyboardMarkup(rows)


def summary(sel):
    c = CATALOG[sel["c"]]
    p = c["plans"][sel["p"]]
    stock = stock_of(sel["c"], sel["p"])
    total = p["price"] * sel["qty"]
    text = (
        "Select quantity\n"
        "--------------------\n"
        f"Product: {c['name']}\n"
        f"Plan: {p['name']}\n"
        f"Price: ${p['price']:.2f} each\n"
        f"In stock: {stock}\n"
        "--------------------\n"
        f"Quantity: {sel['qty']}\n"
        f"Total: ${total:.2f}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Enter quantity", callback_data="qty")],
        [InlineKeyboardButton("Pay (ABA PAY)", callback_data="pay")],
        [InlineKeyboardButton("Back", callback_data=f"cat:{sel['c']}")],
    ])
    return text, markup


async def show(q, context, text, markup):
    if q.message.photo:
        await q.message.delete()
        await context.bot.send_message(q.message.chat_id, text, reply_markup=markup)
    else:
        await q.edit_message_text(text, reply_markup=markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([["BUY NOW"]], resize_keyboard=True)
    await update.message.reply_text(
        f"Hello {update.effective_user.first_name}\n"
        f"Welcome to {STORE_NAME}. Feel free to browse our products below.",
        reply_markup=kb,
    )


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Choose a category", reply_markup=categories_markup())


async def on_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await show(q, context, "Choose a category", categories_markup())


async def on_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = q.data.split(":")[1]
    c = CATALOG[cid]
    rows = [
        [InlineKeyboardButton(
            f"{p['name']} (${p['price']:.2f}) [Stock: {stock_of(cid, pid)}]",
            callback_data=f"plan:{cid}:{pid}")]
        for pid, p in c["plans"].items()
    ]
    rows.append([InlineKeyboardButton("Back (Category)", callback_data="home")])
    text = f"{c['name']}\n\n{c.get('desc', '')}\n\nChoose a plan:"
    markup = InlineKeyboardMarkup(rows)
    photo = c.get("photo")
    if photo:
        await q.message.delete()
        await context.bot.send_photo(q.message.chat_id, photo, caption=text,
                                     reply_markup=markup)
    else:
        await show(q, context, text, markup)


async def on_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, cid, pid = q.data.split(":")
    if stock_of(cid, pid) < 1:
        await q.answer("Out of stock", show_alert=True)
        return
    context.user_data["sel"] = {"c": cid, "p": pid, "qty": 1}
    text, markup = summary(context.user_data["sel"])
    await show(q, context, text, markup)


async def on_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["await_qty"] = True
    await q.message.reply_text("Type the quantity you want (number only):")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("await_qty"):
        return
    sel = context.user_data.get("sel")
    stock = stock_of(sel["c"], sel["p"])
    t = update.message.text.strip()
    if not t.isdigit() or not (1 <= int(t) <= stock):
        await update.message.reply_text(f"Please type a number from 1 to {stock}")
        return
    sel["qty"] = int(t)
    context.user_data["await_qty"] = False
    text, markup = summary(sel)
    await update.message.reply_text(text, reply_markup=markup)


async def on_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sel = context.user_data.get("sel")
    if not sel:
        await q.message.reply_text("Please tap BUY NOW again.")
        return
    if sel["qty"] > stock_of(sel["c"], sel["p"]):
        await q.answer("Not enough stock", show_alert=True)
        return
    p = CATALOG[sel["c"]]["plans"][sel["p"]]
    total = p["price"] * sel["qty"]
    context.user_data["await_receipt"] = True
    await q.message.reply_text(
        f"Please pay ${total:.2f} to:\n{PAYMENT_INFO}\n\n"
        "After paying, send the payment screenshot here."
    )


async def on_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sel = context.user_data.get("sel")
    if not (sel and context.user_data.get("await_receipt")):
        await update.message.reply_text("Please tap BUY NOW to choose a product first.")
        return
    admin = get_admin()
    if admin is None:
        await update.message.reply_text("Store is not ready yet. Please try later.")
        return
    user = update.effective_user
    oid = uuid.uuid4().hex[:8]
    ORDERS[oid] = {"uid": user.id, **sel}
    c = CATALOG[sel["c"]]
    p = c["plans"][sel["p"]]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Approve", callback_data=f"ok:{oid}"),
        InlineKeyboardButton("Reject", callback_data=f"no:{oid}"),
    ]])
    await context.bot.send_photo(
        admin, update.message.photo[-1].file_id,
        caption=(f"New order #{oid}\nBuyer: {user.full_name} (@{user.username})\n"
                 f"{c['name']} / {p['name']} x{sel['qty']} = ${p['price'] * sel['qty']:.2f}"),
        reply_markup=kb,
    )
    context.user_data["await_receipt"] = False
    await update.message.reply_text("Receipt received. Please wait while we verify.")


async def on_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != get_admin():
        await q.answer("Not allowed", show_alert=True)
        return
    await q.answer()
    action, oid = q.data.split(":")
    order = ORDERS.pop(oid, None)
    if not order:
        await q.message.reply_text("This order was already handled.")
        return
    if action == "ok":
        stock = load_stock()
        key = f"{order['c']}:{order['p']}"
        items = stock.get(key, [])
        if len(items) < order["qty"]:
            await q.message.reply_text("Not enough stock. Add more with /addkeys")
            ORDERS[oid] = order
            return
        sent, stock[key] = items[:order["qty"]], items[order["qty"]:]
        save_stock(stock)
        await context.bot.send_message(
            order["uid"],
            "Payment confirmed! Here is your item:\n\n" + "\n".join(sent)
            + "\n\nThank you!",
        )
        await q.edit_message_caption(q.message.caption + "\n\nAPPROVED")
    else:
        await context.bot.send_message(
            order["uid"], "Payment could not be verified. Please contact the seller.")
        await q.edit_message_caption(q.message.caption + "\n\nREJECTED")


async def claim_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_admin() is not None:
        await update.message.reply_text("An admin already exists.")
        return
    with open(ADMIN_FILE, "w", encoding="utf-8") as f:
        json.dump({"id": update.effective_user.id}, f)
    await update.message.reply_text("You are now the admin.")


async def add_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != get_admin():
        return
    lines = update.message.text.split("\n")
    head = lines[0].split()
    if len(head) != 3 or head[1] not in CATALOG or head[2] not in CATALOG[head[1]]["plans"]:
        await update.message.reply_text("Usage:\n/addkeys c1 p1\nKEY-AAAA\nKEY-BBBB")
        return
    new = [k.strip() for k in lines[1:] if k.strip()]
    stock = load_stock()
    key = f"{head[1]}:{head[2]}"
    stock.setdefault(key, []).extend(new)
    save_stock(stock)
    await update.message.reply_text(f"Added {len(new)}. Total stock: {len(stock[key])}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claimadmin", claim_admin))
    app.add_handler(CommandHandler("addkeys", add_keys))
    app.add_handler(MessageHandler(filters.Regex("BUY NOW"), show_categories))
    app.add_handler(CallbackQueryHandler(on_home, pattern=r"^home$"))
    app.add_handler(CallbackQueryHandler(on_category, pattern=r"^cat:"))
    app.add_handler(CallbackQueryHandler(on_plan, pattern=r"^plan:"))
    app.add_handler(CallbackQueryHandler(on_qty, pattern=r"^qty$"))
    app.add_handler(CallbackQueryHandler(on_pay, pattern=r"^pay$"))
    app.add_handler(CallbackQueryHandler(on_admin, pattern=r"^(ok|no):"))
    app.add_handler(MessageHandler(filters.PHOTO, on_receipt))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()


if __name__ == "__main__":
    main()
