"""Assembles the DocumentPayload shape (pages + blocks + entities) the
review screen renders both document panes from — real rendered page images,
with entity boxes (see Entity.boxes) drawn on top as overlays positioned by
percentage of each page's width/height."""
from .serializers import EntitySerializer


def build_document_payload(job):
    pages_out = [
        {
            "number": page.number, "width": page.width, "height": page.height,
            # The image endpoint is addressed by page number, not by the
            # underlying file, so its URL string is otherwise identical
            # before and after complete_job() replaces every Page row with
            # a fresh render of the finalized PDF (see documents/complete.py)
            # — the browser has no reason to refetch a URL it already has
            # cached in memory. `?v=<page id>` ties the URL to the row that
            # currently backs it: a new Page (a new id) always means a new
            # URL, so the frontend's per-image effect (keyed on this exact
            # string) re-fetches exactly when, and only when, the pixels
            # actually changed.
            "image_url": f"/api/jobs/{job.id}/pages/{page.number}/image/?v={page.id}",
        }
        for page in job.page_images.order_by("number")
    ]

    blocks_out = []
    entities_qs = list(job.entities.select_related("block").order_by("block__index", "start_in_block"))

    entities_by_block = {}
    for entity in entities_qs:
        entities_by_block.setdefault(entity.block_id, []).append(entity)

    for block in job.blocks.order_by("index"):
        parts = []
        cursor = 0
        for entity in entities_by_block.get(block.id, []):
            if entity.start_in_block > cursor:
                parts.append({"text": block.text[cursor:entity.start_in_block]})
            parts.append({"entity": entity.code})
            cursor = entity.end_in_block
        if cursor < len(block.text):
            parts.append({"text": block.text[cursor:]})
        blocks_out.append({
            "index": block.index, "page": block.page, "type": block.type,
            "source": block.source, "parts": parts,
        })

    return {
        "pages": pages_out,
        "blocks": blocks_out,
        "entities": EntitySerializer(entities_qs, many=True).data,
    }
