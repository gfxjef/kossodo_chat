from typing import Any, Dict, Optional

from app.db.repositories.conversation import ContactRepository
from app.services.tools.base import BaseTool, ToolResult
from app.services.tools.registry import ToolRegistry


@ToolRegistry.register
class SaveContactTool(BaseTool):
    """Tool to save client contact information."""

    name = "save_contact"
    description = (
        "Save or update the client's contact information. "
        "Use this when the client provides their name, phone, email, company name, or RUC/DNI. "
        "You can call this multiple times as the client provides more information. "
        "RUC (11 digits) is for businesses, DNI (8 digits) is for individuals."
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The client's full name",
                },
                "phone": {
                    "type": "string",
                    "description": "The client's phone number",
                },
                "email": {
                    "type": "string",
                    "description": "The client's email address",
                },
                "company_name": {
                    "type": "string",
                    "description": "The name of the client's company or organization",
                },
                "ruc_dni": {
                    "type": "string",
                    "description": "The client's RUC (business tax ID, 11 digits) or DNI (personal ID, 8 digits)",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        company_name: Optional[str] = None,
        ruc_dni: Optional[str] = None,
    ) -> ToolResult:
        """Execute the tool to save contact information."""
        if not any([name, phone, email, company_name, ruc_dni]):
            return ToolResult(
                success=False,
                message="At least one contact field must be provided.",
            )

        repo = ContactRepository(self.session)
        contact = await repo.upsert_contact(
            conversation_id=self.conversation_id,
            name=name,
            phone=phone,
            email=email,
            company_name=company_name,
            ruc_dni=ruc_dni,
        )

        saved_fields = []
        if name:
            saved_fields.append(f"name: {name}")
        if phone:
            saved_fields.append(f"phone: {phone}")
        if email:
            saved_fields.append(f"email: {email}")
        if company_name:
            saved_fields.append(f"company: {company_name}")
        if ruc_dni:
            saved_fields.append(f"ruc_dni: {ruc_dni}")

        return ToolResult(
            success=True,
            data={
                "contact_id": contact.id,
                "name": contact.name,
                "phone": contact.phone,
                "email": contact.email,
                "company_name": contact.company_name,
                "ruc_dni": contact.ruc_dni,
            },
            message=f"Contact information saved: {', '.join(saved_fields)}.",
        )
