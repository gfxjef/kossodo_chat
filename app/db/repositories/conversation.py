from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.db.repositories.base import BaseRepository
from app.models.database import Contact, Conversation, ConversationStatus, Inquiry, Message


class ConversationRepository(BaseRepository[Conversation]):
    """Repository for conversation operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)

    async def get_by_session_id(self, session_id: str) -> Optional[Conversation]:
        """Get conversation by session ID with all related data."""
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .options(
                selectinload(Conversation.messages),
                selectinload(Conversation.contact),
                selectinload(Conversation.inquiry),
            )
        )
        return result.scalar_one_or_none()

    async def create_conversation(self, session_id: str) -> Conversation:
        """Create a new conversation."""
        return await self.create(session_id=session_id)

    async def set_company(self, conversation: Conversation, company: str) -> Conversation:
        """Set the company for a conversation."""
        return await self.update(conversation, company=company)

    async def set_status(self, conversation: Conversation, status: str) -> Conversation:
        """Set the status of a conversation."""
        return await self.update(conversation, status=status)

    def is_expired(self, conversation: Conversation) -> bool:
        """Check if conversation has expired due to inactivity."""
        if conversation.status != ConversationStatus.ACTIVE.value:
            return False

        # Use local time for comparison since SQLite stores local timestamps
        now = datetime.now()
        updated_at = conversation.updated_at

        # Remove timezone info if present for consistent comparison
        if updated_at.tzinfo is not None:
            updated_at = updated_at.replace(tzinfo=None)

        idle_limit = timedelta(seconds=settings.conversation_idle_timeout_seconds)
        return (now - updated_at) > idle_limit

    async def expire_conversation(self, conversation: Conversation) -> Conversation:
        """Mark conversation as expired."""
        return await self.update(conversation, status=ConversationStatus.EXPIRED.value)


class MessageRepository(BaseRepository[Message]):
    """Repository for message operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Message, session)

    async def add_message(
        self, conversation_id: int, role: str, content: str
    ) -> Message:
        """Add a message to a conversation."""
        return await self.create(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )

    async def get_conversation_messages(
        self, conversation_id: int
    ) -> List[Message]:
        """Get all messages for a conversation."""
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())


class ContactRepository(BaseRepository[Contact]):
    """Repository for contact operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Contact, session)

    async def get_by_conversation_id(self, conversation_id: int) -> Optional[Contact]:
        """Get contact by conversation ID."""
        result = await self.session.execute(
            select(Contact).where(Contact.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def upsert_contact(
        self,
        conversation_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        company_name: Optional[str] = None,
        ruc_dni: Optional[str] = None,
    ) -> Contact:
        """Create or update contact for a conversation."""
        existing = await self.get_by_conversation_id(conversation_id)

        if existing:
            update_data = {}
            if name is not None:
                update_data["name"] = name
            if phone is not None:
                update_data["phone"] = phone
            if email is not None:
                update_data["email"] = email
            if company_name is not None:
                update_data["company_name"] = company_name
            if ruc_dni is not None:
                update_data["ruc_dni"] = ruc_dni

            if update_data:
                return await self.update(existing, **update_data)
            return existing
        else:
            return await self.create(
                conversation_id=conversation_id,
                name=name,
                phone=phone,
                email=email,
                company_name=company_name,
                ruc_dni=ruc_dni,
            )


class InquiryRepository(BaseRepository[Inquiry]):
    """Repository for inquiry operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Inquiry, session)

    async def get_by_conversation_id(self, conversation_id: int) -> Optional[Inquiry]:
        """Get inquiry by conversation ID."""
        result = await self.session.execute(
            select(Inquiry).where(Inquiry.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def upsert_inquiry(
        self, conversation_id: int, description: str
    ) -> Inquiry:
        """Create or update inquiry for a conversation."""
        existing = await self.get_by_conversation_id(conversation_id)

        if existing:
            return await self.update(existing, description=description)
        else:
            return await self.create(
                conversation_id=conversation_id,
                description=description,
            )
