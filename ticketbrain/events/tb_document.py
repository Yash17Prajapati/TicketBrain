import frappe


def on_document_submitted(doc, method):
    """Trigger document processing after a TB Document is inserted."""
    try:
        frappe.enqueue(
            "ticketbrain.ai.document_processor.process_document",
            doc_name=doc.name,
            queue="long",
            timeout=600,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Document enqueue failed")
