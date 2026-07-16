import os
import logging
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
from functools import wraps
import hashlib

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://localhost/discord_logger')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

db = SQLAlchemy(app)
CORS(app, supports_credentials=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(255), primary_key=True)
    username = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255))
    avatar_url = db.Column(db.String(512))
    bio = db.Column(db.Text)
    logged_by_tokens = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('Message', backref='user', lazy=True)
    name_history = db.relationship('NameHistory', backref='user', lazy=True)
    avatar_history = db.relationship('AvatarHistory', backref='user', lazy=True)
    ips = db.relationship('IP', backref='user', lazy=True)
    servers = db.relationship('Server', secondary='user_servers', backref='members')

class NameHistory(db.Model):
    __tablename__ = 'name_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey('users.id'), nullable=False)
    old_name = db.Column(db.String(255), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

class AvatarHistory(db.Model):
    __tablename__ = 'avatar_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey('users.id'), nullable=False)
    avatar_url = db.Column(db.String(512), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

class IP(db.Model):
    __tablename__ = 'ips'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)

class Server(db.Model):
    __tablename__ = 'servers'
    id = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    icon_url = db.Column(db.String(512))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('Message', backref='server', lazy=True)
    channels = db.relationship('Channel', backref='server', lazy=True)

class Channel(db.Model):
    __tablename__ = 'channels'
    id = db.Column(db.String(255), primary_key=True)
    server_id = db.Column(db.String(255), db.ForeignKey('servers.id'), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    is_dm = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='channel', lazy=True)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.String(255), primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey('users.id'), nullable=False)
    server_id = db.Column(db.String(255), db.ForeignKey('servers.id'), nullable=True)
    channel_id = db.Column(db.String(255), db.ForeignKey('channels.id'), nullable=False)
    content = db.Column(db.Text)
    logged_by_token = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

user_servers = db.Table('user_servers',
    db.Column('user_id', db.String(255), db.ForeignKey('users.id')),
    db.Column('server_id', db.String(255), db.ForeignKey('servers.id'))
)

class TokenSession(db.Model):
    __tablename__ = 'token_sessions'
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

# Authentication
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        try:
            token = token.replace('Bearer ', '')
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            session_data = TokenSession.query.filter_by(token_hash=token_hash).first()
            if not session_data:
                return jsonify({'error': 'Invalid token'}), 401
            session_data.last_activity = datetime.utcnow()
            db.session.commit()
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Auth error: {str(e)}")
            return jsonify({'error': 'Authentication failed'}), 401
    return decorated

# Routes
@app.route('/health', methods=['GET'])
def health():
    try:
        db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        token = data.get('token')
        if not token:
            return jsonify({'error': 'No token provided'}), 400
        
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        existing = TokenSession.query.filter_by(token_hash=token_hash).first()
        if existing:
            return jsonify({'success': True, 'message': 'Token already registered'}), 200
        
        session_obj = TokenSession(
            token_hash=token_hash,
            user_id='pending'
        )
        db.session.add(session_obj)
        db.session.commit()
        
        return jsonify({'success': True, 'token_hash': token_hash}), 200
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/search', methods=['GET'])
@token_required
def search_users():
    try:
        query = request.args.get('q', '').lower()
        limit = int(request.args.get('limit', 50))
        
        if not query:
            return jsonify({'error': 'Query required'}), 400
        
        users = User.query.filter(
            db.or_(
                User.id.ilike(f'%{query}%'),
                User.username.ilike(f'%{query}%'),
                User.display_name.ilike(f'%{query}%')
            )
        ).limit(limit).all()
        
        return jsonify([{
            'id': u.id,
            'username': u.username,
            'display_name': u.display_name,
            'avatar_url': u.avatar_url,
            'bio': u.bio
        } for u in users]), 200
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['GET'])
@token_required
def get_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'id': user.id,
            'username': user.username,
            'display_name': user.display_name,
            'avatar_url': user.avatar_url,
            'bio': user.bio,
            'created_at': user.created_at.isoformat(),
            'logged_by_tokens': user.logged_by_tokens,
            'message_count': len(user.messages),
            'server_count': len(user.servers),
            'name_history': [{'name': nh.old_name, 'changed_at': nh.changed_at.isoformat()} for nh in user.name_history],
            'avatar_history': [{'url': ah.avatar_url, 'changed_at': ah.changed_at.isoformat()} for ah in user.avatar_history],
            'ips': [ip.ip_address for ip in user.ips]
        }), 200
    except Exception as e:
        logger.error(f"Get user error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>/messages', methods=['GET'])
@token_required
def get_user_messages(user_id):
    try:
        channel_id = request.args.get('channel_id')
        keyword = request.args.get('keyword', '').lower()
        limit = int(request.args.get('limit', 100))
        page = int(request.args.get('page', 1))
        offset = (page - 1) * limit
        
        query = Message.query.filter_by(user_id=user_id)
        
        if channel_id:
            query = query.filter_by(channel_id=channel_id)
        
        if keyword:
            query = query.filter(Message.content.ilike(f'%{keyword}%'))
        
        total = query.count()
        messages = query.order_by(Message.created_at.desc()).limit(limit).offset(offset).all()
        
        return jsonify({
            'total': total,
            'page': page,
            'limit': limit,
            'messages': [{
                'id': m.id,
                'content': m.content,
                'channel_id': m.channel_id,
                'server_id': m.server_id,
                'created_at': m.created_at.isoformat(),
                'logged_by_token': m.logged_by_token
            } for m in messages]
        }), 200
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard', methods=['GET'])
@token_required
def dashboard():
    try:
        total_users = User.query.count()
        total_messages = Message.query.count()
        total_servers = Server.query.count()
        unique_ips = db.session.query(db.func.count(db.distinct(IP.ip_address))).scalar()
        
        return jsonify({
            'total_users': total_users,
            'total_messages': total_messages,
            'total_servers': total_servers,
            'logged_ips': unique_ips,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/servers', methods=['GET'])
@token_required
def get_servers():
    try:
        servers = Server.query.all()
        return jsonify([{
            'id': s.id,
            'name': s.name,
            'icon_url': s.icon_url,
            'message_count': len(s.messages),
            'member_count': len(s.members)
        } for s in servers]), 200
    except Exception as e:
        logger.error(f"Get servers error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal error: {str(e)}")
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
