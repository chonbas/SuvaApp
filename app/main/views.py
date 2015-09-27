from flask import render_template, redirect, url_for, abort, flash, request,\
    current_app, make_response, g
from flask.ext.login import login_required, current_user
from flask.ext.sqlalchemy import get_debug_queries
from . import main
from .forms import EditProfileForm, EditProfileAdminForm, PostForm,CommentForm, SearchForm
from .. import db, Whoosh
from ..models import User, Post, Comment, Tag, tagged_posts
from ..helpers import extract_tags, clean_tags

@main.before_app_request
def before_request():
    g.search_form = SearchForm()

@main.route('/search', methods=['POST'])
def search():
    if not g.search_form.validate_on_submit():
        return redirect(url_for('main.index'))
    return redirect(url_for('.search_results', query=g.search_form.search.data))

@main.route('/search_results/<query>')
def search_results(query):
        page = request.args.get('page', 1, type=int)
        pagination = Post.query.whoosh_search(query, limit=current_app.config['MAX_SEARCH_RESULTS']).paginate(
            page, per_page=current_app.config['POSTS_PER_PAGE'],
            error_out=False)
        posts = pagination.items
        flash("Search completed for " + query)
        return render_template('index.html',
                           posts=posts,
                           pagination=pagination, logo=False)


@main.route('/', methods=['GET', 'POST'])
def index():
    page = request.args.get('page', 1, type=int)
    pagination = Post.query.order_by(Post.timestamp.desc()).paginate(
        page, per_page=current_app.config['POSTS_PER_PAGE'],
        error_out=False)
    posts = pagination.items
    return render_template('index.html', posts=posts, pagination=pagination, logo=True)


@main.route('/newpost', methods=['GET', 'POST'])
@login_required
def newpost():
    if not current_user.is_administrator:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        slug = form.slug.data
        if slug is not None:
            slug = form.body.data[:current_app.config['DEFAULT_SLUG_CHARS']] + '...'
        post = Post(title=form.title.data,
                    body=form.body.data, slug=slug,
                    author=current_user._get_current_object())
        if form.tags.data is not None:
            tagList = extract_tags(form.tags.data)
            for stringTag in tagList:
                tag = Tag.query.filter_by(name=stringTag).first()
                if not tag:
                    tag = Tag(name=stringTag)
                    db.session.add(tag)
                post.tags.append(tag)
        db.session.add(post)
        return redirect(url_for('.index'))
    return render_template('new_post.html', form=form)


@main.route('/user/<username>', methods=['GET', 'POST'])
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template('user.html', user=user)

@main.route('/about', methods=['GET', 'POST'])
def about():
    user = User.query.filter_by(email=current_app.config['BLOG_ADMIN']).first_or_404()
    return render_template('about.html', user=user)

@main.route('/contact', methods=['GET', 'POST'])
def contact():
    return render_template('contact.html')

@main.route('/about_site')
def about_site():
    return render_template('aboutsite.html')

@main.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.location = form.location.data
        current_user.about_me = form.about_me.data
        db.session.add(current_user)
        flash('Your profile has been updated.')
        return redirect(url_for('.user', username=current_user.username))
    form.name.data = current_user.name
    form.location.data = current_user.location
    form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', form=form)


@main.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_profile_admin(id):
    if not current_user.is_administrator:
        abort(403)
    user = User.query.get_or_404(id)
    form = EditProfileAdminForm(user=user)
    if form.validate_on_submit():
        user.email = form.email.data
        user.username = form.username.data
        user.name = form.name.data
        user.location = form.location.data
        user.about_me = form.about_me.data
        db.session.add(user)
        flash('The profile has been updated.')
        return redirect(url_for('.about', username=user.username))
    form.email.data = user.email
    form.username.data = user.username
    form.name.data = user.name
    form.location.data = user.location
    form.about_me.data = user.about_me
    return render_template('edit_profile.html', form=form, user=user)

@main.route('/post/<int:id>', methods=['GET', 'POST'])
def post(id):
    post = Post.query.get_or_404(id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(body=form.body.data,
                          post=post,
                          author=form.author.data,
                          author_url=form.author_url.data)
        db.session.add(comment)
        flash('Your comment has been published.')
        return redirect(url_for('.post', id=post.id, page=1))
    page = request.args.get('page', 1, type=int)
    if page == -1:
        page = (post.comments.count() - 1) / \
            current_app.config['COMMENTS_PER_PAGE'] + 1
    pagination = post.comments.order_by(Comment.timestamp.desc()).paginate(
        page, per_page=current_app.config['COMMENTS_PER_PAGE'],
        error_out=False)
    comments = pagination.items
    return render_template('post.html', posts=[post], post=post, form=form,
                           comments=comments, pagination=pagination)

@main.route('/sort/<string:tag_name>', methods=['GET', 'POST'])
def sort(tag_name):
    page = request.args.get('page', 1, type=int)
    pagination = Post.query.filter(Post.tags.any(name=tag_name)).paginate(
        page, per_page=current_app.config['POSTS_PER_PAGE'],
        error_out=False)
    posts = pagination.items
    return render_template('index.html', posts=posts, pagination=pagination, logo=False)

@main.route('/untag/<int:post_id>_<string:tag_name>', methods=['GET', 'POST'])
@login_required
def untag(post_id, tag_name):
    post = Post.query.get_or_404(post_id)
    tag = post.getTag(tag_name)
    post.tags.remove(tag)
    return redirect(url_for('.edit', id=post_id))

@main.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    post = Post.query.get_or_404(id)
    if not current_user.is_administrator:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        if form.tags.data is not None:
            tagList = extract_tags(form.tags.data)
            for stringTag in tagList:
                tag = Tag.query.filter_by(name=stringTag).first()
                if not tag:
                    tag = Tag(name=stringTag)
                    db.session.add(tag)
                    post.tags.append(tag)
        post.body = form.body.data
        slug = form.slug.data
        if slug is not None:
            slug = form.body.data[:current_app.config['DEFAULT_SLUG_CHARS']]
        post.slug = slug
        post.title = form.title.data
        db.session.add(post)
        flash('The post has been updated.')
        return redirect(url_for('.post', id=post.id))
    form.title.data = post.title
    form.slug.data = post.slug
    form.body.data = post.body
    return render_template('edit_post.html', form=form, post=post.id, tags=post.tags)

@main.route('/togglepostcomments/<int:id>', methods=['GET', 'POST'])
@login_required
def toggle_post_comments(id):
    if not current_user.is_administrator:
        abort(403)
    post = Post.query.get_or_404(id)
    if post.comments_enabled:
        post.comments_enabled = False
        flash('Comments for this post have been disabled.')
    else:
        post.comments_enabled = True
        flash('Comments for this post have been enabled.')
    db.session.add(post)
    return redirect(url_for('.post', id=post.id))

@main.route('/togglecomment/<int:post_id><int:comment_id>', methods=['GET','POST'])
@login_required
def toggle_comment(post_id, comment_id):
    if not current_user.is_administrator:
        abort(403)
    comment = Comment.query.get_or_404(comment_id)
    post = Post.query.get_or_404(post_id)
    if comment.disabled:
        comment.disabled = False;
        flash('This comment has been disabled.')
    else:
        comment.disabled = True;
        flash('This comment has been enabled.')
    db.session.add(comment)
    return redirect(url_for('.post', id=post.id))
