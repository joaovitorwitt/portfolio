import logging

from flask import Blueprint, jsonify

from website.db import ContentRepository

log = logging.getLogger(__name__)

bp = Blueprint('pages', __name__)

repository = ContentRepository()


@bp.route('/health')
def health():
    return jsonify({'status': 'ok'})
