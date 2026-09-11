"""Assembles the DocumentPayload shape (pages + blocks + entities) the
review screen renders both document panes from — real rendered page images,
with entity boxes (see Entity.boxes) drawn on top as overlays positioned by
percentage of each page's width/height."""
from .serializers import EntitySerializer


def build_document_payload(job):
    pages_out = [
        {
            "number": page.number, "width": page.width, "height": page.height,
            "image_url": f"/api/jobs/{job.id}/pages/{page.number}/image/",
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
