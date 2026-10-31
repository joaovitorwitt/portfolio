import logging

from flask import Blueprint, jsonify, render_template

from website.db import ContentRepository

log = logging.getLogger(__name__)

bp = Blueprint('pages', __name__)

repository = ContentRepository()


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/health')
def health():
    return jsonify({'status': 'ok'})
