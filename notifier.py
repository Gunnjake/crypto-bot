# notifier.py
from discord_webhook import DiscordWebhook, DiscordEmbed
from config import DISCORD_WEBHOOK_URL, NOTIFICATION_BALANCE_THRESHOLD
from datetime import datetime

# Architectural Choice: Decoupled Notification Module.
# This module handles all external communication (in this case, to Discord).
# If we wanted to add email or SMS notifications, we could simply add new functions
# here without changing the main bot logic.

def send_error_notification(error_message):
    """
    Sends a high-priority, formatted error message to the configured Discord webhook.
    Includes an "@everyone" ping to ensure immediate attention.
    """
    # Do not send if the webhook URL is not configured
    if not DISCORD_WEBHOOK_URL or 'YOUR_WEBHOOK_URL_HERE' in DISCORD_WEBHOOK_URL:
        return
    
    webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL, content="@everyone")
    embed = DiscordEmbed(title='🚨 BOT ERROR 🚨', description="The bot has encountered a fatal error...", color='ff0000')
    embed.add_embed_field(name='Error Details', value=f"```{error_message}```")
    embed.set_timestamp()
    webhook.add_embed(embed)
    try:
        webhook.execute()
    except Exception as e:
        print(f"Failed to send Discord error notification: {e}")

def send_daily_summary(current_total, previous_total, balances):
    """
    Constructs and sends a detailed daily portfolio summary to Discord, including
    total value change and a breakdown of individual asset performance.
    
    Args:
        current_total (float): The current total portfolio value.
        previous_total (float): The portfolio value from the previous day's log.
        balances (list): The list of enriched balance objects from the client.
    """
    if not DISCORD_WEBHOOK_URL or 'YOUR_WEBHOOK_URL_HERE' in DISCORD_WEBHOOK_URL:
        return
    
    # --- 1. Calculate Total Portfolio Change ---
    total_change_usd = current_total - previous_total
    total_change_pct = (total_change_usd / previous_total) * 100 if previous_total > 0 else 0
    total_change_sign = "+" if total_change_usd >= 0 else ""
    
    portfolio_summary = (
        f"```\n"
        f"Current:  ${current_total:,.2f}\n"
        f"Previous: ${previous_total:,.2f}\n"
        f"Change:   {total_change_sign}${total_change_usd:,.2f} ({total_change_sign}{total_change_pct:.2f}%)\n"
        f"```"
    )

    # --- 2. Build the Formatted Coin Breakdown String ---
    coin_breakdown_lines = []
    # Sort balances by USD value to show the most significant assets first
    for b in sorted(balances, key=lambda x: x.get('usd_value', 0), reverse=True):
        if b['usd_value'] > NOTIFICATION_BALANCE_THRESHOLD and b['asset'] != 'USDT':
            pnl_24h = b.get('pnl_24h', 0)
            pnl_24h_pct = b.get('pnl_24h_pct', 0)
            pnl_sign_24h = "+" if pnl_24h >= 0 else ""
            quantity = b.get('quantity', 0)

            # Create a multi-line entry for each coin for readability
            coin_breakdown_lines.append(f"{b['asset']}: ${b['usd_value']:,.2f} ({quantity:,.6f} {b['asset']})")
            coin_breakdown_lines.append(f"Change: {pnl_sign_24h}${pnl_24h:,.2f} ({pnl_sign_24h}{pnl_24h_pct:.2f}%)")

    coin_breakdown_summary = "\n".join(coin_breakdown_lines)
    if coin_breakdown_summary:
        coin_breakdown_summary = f"```markdown\n{coin_breakdown_summary}\n```"

    # --- 3. Create and Send the Discord Embed ---
    webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL)
    
    embed = DiscordEmbed(title="Daily Portfolio Summary", color='0099ff')
    embed.add_embed_field(name="Total Portfolio Value", value=portfolio_summary, inline=False)
    
    if coin_breakdown_summary:
        embed.add_embed_field(name="Coin Breakdown (24h Change)", value=coin_breakdown_summary, inline=False)
        
    embed.set_timestamp()
    
    webhook.add_embed(embed)
    try:
        webhook.execute()
    except Exception as e:
        print(f"Failed to send Discord daily summary: {e}")
