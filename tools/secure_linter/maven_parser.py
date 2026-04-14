from lxml import etree
import re
import io
import logging

logger = logging.getLogger(__name__)

def parse_pom(file_path):
    try:
        raw_bytes = open(file_path, 'rb').read()
        text = raw_bytes.decode('utf-8', errors='ignore')
        text = re.sub(r'<\?xml[^>]*\?>', '', text)

        cleaned = "\n".join(
            re.sub(r'^\s*\d+:\s*', '', line)
            for line in text.splitlines()
        )

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(io.BytesIO(cleaned.encode('utf-8')), parser)
        root = tree.getroot()
        logger.debug("parse_pom: root tag <%s>", root.tag)

        return root

    except Exception as e:
        logger.warning("parse_pom: failed to parse %s: %s", file_path, e)
        return None