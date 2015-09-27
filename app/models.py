from datetime import datetime
import hashlib, sys
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from markdown import markdown
import bleach
from flask import current_app, request, url_for
from flask.ext.login import UserMixin, AnonymousUserMixin
from . import db, login_manager, Whoosh

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    admin = db.Column(db.Boolean)
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(64))
    location = db.Column(db.String(64))
    about_me = db.Column(db.Text())
    posts = db.relationship('Post', backref='author', lazy='dynamic')

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.email == current_app.config['BLOG_ADMIN']:
                self.admin = True

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_administrator(self):
        return self.admin

    def ping(self):
        self.last_seen = datetime.utcnow()
        db.session.add(self)

class AnonymousUser(AnonymousUserMixin):
    def is_administrator(self):
        return False

login_manager.anonymous_user = AnonymousUser

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

tagged_posts = db.Table('tagged_posts',
        db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), nullable=False),
        db.Column('post_id', db.Integer, db.ForeignKey('posts.id'), nullable=False),
        db.PrimaryKeyConstraint('post_id', 'tag_id')
)

class Post(db.Model):
    __tablename__ = 'posts'
    __searchable__ = ['title', 'body', 'slug']

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128))
    body = db.Column(db.Text)
    slug = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comments_enabled = db.Column(db.Boolean, default=True)
    comments = db.relationship('Comment', backref='post', lazy='dynamic')
    tags = db.relationship('Tag', secondary=tagged_posts,
                              backref=db.backref('posts', lazy='dynamic'))
    def __repr__(self):
        return '{0}(title={1})'.format(self.__class__.__name__, self.title)

    def getTag(self, query):
        for tag in self.tags:
            if tag is not None:
                if tag.name == query:
                    return tag
        return None

class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

    def __repr__(self):
        return '%s' %self.name

class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    author = db.Column(db.String(64))
    author_url = db.Column(db.String(64))
    body = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    disabled = db.Column(db.Boolean, default=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'))
