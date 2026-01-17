import asyncio
import aiohttp
import json
import textwrap

import discord

import logging
logger = logging.getLogger(__name__)


WEBHOOK_EMPTY_AVATAR = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/25/0-Background.svg/300px-0-Background.svg.png"
WEBHOOK_EMPTY_NAME = "\u2e33\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2002\u2e33"
MAX_ATTACHMENT_SIZE = 10000000  # 10MB
DISCORD_MESSAGE_LIMIT = 2000
DISCORD_MESSAGE_SAFE_LIMIT = 1964  # 2000 - 36 chars for prefix


def build_webhook_args(
    content: str,
    username: str | None = None,
    avatar_url: str | None = None,
    embeds: list[discord.Embed] | None = None,
    files: list[discord.File] | None = None,
    wait: bool = True
) -> dict:
    """Build webhook send arguments, filtering None values."""
    args = {"content": content, "wait": wait}
    if username is not None:
        args["username"] = username
    if avatar_url is not None:
        args["avatar_url"] = avatar_url
    if embeds is not None:
        args["embeds"] = embeds
    if files is not None:
        args["files"] = files
    return {k: v for k, v in args.items() if v is not None}


def resolve_user_profiles(
    message: discord.Message,
    use_profiles: bool
) -> tuple[str | None, str | None]:
    """Get username and avatar URL based on config and message type."""
    if not use_profiles:
        return None, None

    # Handle system messages
    if message.type not in (discord.MessageType.default, discord.MessageType.reply):
        return WEBHOOK_EMPTY_NAME, WEBHOOK_EMPTY_AVATAR

    # Handle normal messages - replace "Discord" to avoid webhook username restrictions
    username = message.author.display_name.replace("Discord", "D🗪cord").replace("discord", "d🗪cord")
    avatar_url = message.author.display_avatar.url
    return username, avatar_url


async def process_attachments(
    message: discord.Message,
    webhook: discord.Webhook,
    as_url: bool,
    username: str | None,
    avatar_url: str | None,
    max_size: int = MAX_ATTACHMENT_SIZE
) -> tuple[list[discord.File] | None, str]:
    """Process attachments as files or URLs based on config and size.

    Returns:
        tuple: (files_list, additional_content)
            - files_list: List of discord.File objects or None
            - additional_content: Additional content to append to message
    """
    if not message.attachments:
        return None, ""

    additional_content = ""

    # If configured to use URLs, just append URLs to content
    if as_url:
        for attachment in message.attachments:
            additional_content += "\n" + str(attachment.url)
        return None, additional_content

    # Try to upload files
    try:
        # Check total size
        total_size = sum(att.size for att in message.attachments)
        if total_size >= max_size:
            raise AssertionError("Total size exceeds limit")

        # All files fit, create file objects
        files = [await att.to_file() for att in message.attachments]
        return files, additional_content

    except AssertionError:
        # Total too large, try sending individually
        for attachment in message.attachments:
            if attachment.size < max_size:
                try:
                    await webhook.send(
                        username=username,
                        avatar_url=avatar_url,
                        files=[await attachment.to_file()],
                        wait=True
                    )
                except Exception:
                    additional_content += "\n" + str(attachment.url)
            else:
                # File too large, send as URL with message
                await webhook.send(
                    content=f"**Discord:** File too large\n{attachment.url}",
                    username=username,
                    avatar_url=avatar_url,
                    wait=True
                )
        return None, additional_content


async def handle_message_lifecycle(
    webhook: discord.Webhook,
    edit_msg_id: int | None,
    delete_msg_id: int | None,
    message: discord.Message
) -> bool | discord.WebhookMessage:
    """Handle message deletion and editing operations.

    Returns:
        bool | WebhookMessage: False if operation failed, result otherwise
    """
    # Delete the message if requested
    if delete_msg_id is not None:
        try:
            return await webhook.delete_message(delete_msg_id)
        except (discord.HTTPException, discord.NotFound):
            return False

    # Edit the message if requested
    if edit_msg_id is not None:
        try:
            return await webhook.edit_message(
                message_id=edit_msg_id,
                content=message.clean_content
            )
        except discord.HTTPException:
            try:
                return await webhook.edit_message(
                    message_id=edit_msg_id,
                    content="**Discord:** Unsupported content\n" + str(message.clean_content)
                )
            except (discord.HTTPException, discord.NotFound):
                return False

    # No lifecycle operation requested
    return True


async def msgFormatter(self, webhook, message, json, editMsgId=None, deleteMsgId=None):
    """Format and send a message through a webhook.

    Args:
        webhook: A webhook object from discord.py
        message: A message object from discord.py
        json: A dict with config variables (userProfiles, attachsAsUrl)
        editMsgId: Optional message ID to edit
        deleteMsgId: Optional message ID to delete

    Returns:
        WebhookMessage | bool: Sent webhook message or False on failure
    """
    # Handle delete/edit operations first
    lifecycle_result = await handle_message_lifecycle(webhook, editMsgId, deleteMsgId, message)
    if editMsgId is not None or deleteMsgId is not None:
        return lifecycle_result

    # Resolve user profiles (username and avatar)
    username, avatar_url = resolve_user_profiles(message, json.get("userProfiles", True))

    # Determine message content based on message type
    if message.type in (discord.MessageType.default, discord.MessageType.reply):
        msg_content = message.clean_content
    else:
        msg_content = "**Discord:** " + str(message.type)

    # Handle reply if exists
    if message.reference and message.type == discord.MessageType.reply:
        ref_obj = message.reference.resolved
        reply_embed = discord.Embed(color=discord.Color(value=0x25c059), description="")

        # Fallback for missing reference
        if not hasattr(ref_obj, "clean_content"):
            ref_obj = message
            ref_content = "Message not found"
            ref_url = ""
        else:
            ref_content = ref_obj.clean_content
            ref_url = ref_obj.jump_url

        # Create reply preview
        if ref_content:
            reply_body = (ref_content[:56] + '...') if len(ref_content) > 56 else ref_content
        else:
            reply_body = "Click to see attachment 🖼️"

        reply_title = f"↪️ {reply_body}"
        if json.get("userProfiles"):
            reply_embed.set_author(name=reply_title, icon_url=ref_obj.author.display_avatar.url, url=ref_url)
        else:
            reply_embed.set_author(name=reply_title, url=ref_url)

        # Send reply embed before the main message
        await webhook.send(username=username, avatar_url=avatar_url, embed=reply_embed)
        await asyncio.sleep(1)

    # Process embeds (exclude if from HTTP link to fix issue #4)
    embeds = message.embeds if message.embeds and "http" not in msg_content else None

    # Process attachments
    files, attachment_content = await process_attachments(
        message, webhook, json.get("attachsAsUrl", True), username, avatar_url
    )
    msg_content += attachment_content

    # Add activity information
    if message.activity:
        msg_content += f"\n**Discord:** Activity\n{message.activity}"
    if message.application:
        msg_content += f"\n**Discord:** {message.application.name}\n{message.application.description}"

    # Add stickers
    if message.stickers:
        for sticker in message.stickers:
            if sticker.url is not None:
                msg_content += "\n" + str(sticker.url)
            else:
                msg_content += f"\n**Discord:** Sticker\n{sticker.name}, {sticker.id}"

    # Send the main message
    try:
        webhook_message = await webhook.send(
            **build_webhook_args(msg_content, username, avatar_url, embeds, files)
        )
        return webhook_message

    except discord.HTTPException:
        # Handle message too long
        if len(msg_content) > DISCORD_MESSAGE_SAFE_LIMIT:
            msg_lines = textwrap.wrap(msg_content, DISCORD_MESSAGE_LIMIT, break_long_words=True)
            for line in msg_lines:
                webhook_message = await webhook.send(
                    **build_webhook_args(line, username, avatar_url, embeds, files)
                )
            return webhook_message

        # Handle empty or unsupported content
        try:
            unsupported_content = "**Discord:** Unsupported content\n" + str(msg_content[:DISCORD_MESSAGE_SAFE_LIMIT])
            if len(msg_content) > DISCORD_MESSAGE_SAFE_LIMIT:
                unsupported_content += '…'

            webhook_message = await webhook.send(
                **build_webhook_args(unsupported_content, username, avatar_url, embeds, files)
            )
            return webhook_message

        except (discord.HTTPException, discord.NotFound):
            # Last resort: send without custom username/avatar
            try:
                webhook_message = await webhook.send(
                    **build_webhook_args(unsupported_content, "Unknown User", None, embeds, files)
                )
                return webhook_message
            except Exception as err:
                logger.error(f"Failed to send message: {err}")
                return False

    except Exception as err:
        logger.error(f"Unexpected error in msgFormatter: {err}")
        return False


def webhookSettings(json):
    """
    Default settings for sending webhooks
    """
    relayInfo = {
        "toWebhook": json.get("toWebhook", ""),
        "attachsAsUrl": json.get("attachsAsUrl", True),
        "userProfiles": json.get("userProfiles", True),
    }
    return relayInfo


async def webhookFinder(self, channel):
    """Find or create a webhook for the bot in the given channel.

    Returns:
        str | bool: Webhook URL or False on failure
    """
    # Find a webhook that the bot made
    try:
        webhooks = await channel.webhooks()
    except (discord.HTTPException, discord.Forbidden) as err:
        logger.error(f"Could not fetch webhooks: {err}")
        return False

    # Check for existing bot webhook
    for webhook in webhooks:
        if self.bot.user == webhook.user:
            return webhook.url

    # No existing webhook found, create one
    try:
        new_webhook = await channel.create_webhook(name="Webhook")
        return new_webhook.url
    except (discord.HTTPException, discord.Forbidden) as err:
        logger.error(f"Could not create webhook: {err}")
        return False
