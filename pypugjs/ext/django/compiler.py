import os
from django.conf import settings
from django.utils.encoding import force_text as to_text
from django.utils.translation import template

from pypugjs import Compiler as _Compiler, register_filter
from pypugjs.exceptions import CurrentlyNotSupported
from pypugjs.utils import process


class Compiler(_Compiler):
    auto_close_code = [
        'autoescape',
        'cache',
        'comment',
        'compress',
        'block',
        'blocktrans',
        'filter',
        'for',
        'if',
        'ifchanged',
        'ifequal',
        'ifnotequal',
        'localize',
        'spaceless',
        'trans',
        'with',
        'verbatim',
    ]
    useRuntime = True

    def __init__(self, node, **options):
        if settings.configured:
            options.update(getattr(settings, 'PYPUGJS', {}))
        self.base_directory = options.get('base_directory', None)
        super(Compiler, self).__init__(node, **options)

    def _getRealFilePath(self, path):
        if os.path.exists(path):
            return path
        if not self.base_directory:
            return None
        path = os.path.join(self.base_directory, path)
        if os.path.exists(path):
            return path

    def visitCodeBlock(self, block):
        self.buffer('{%% block %s %%}' % block.name)
        if block.mode == 'append':
            self.buffer('{{block.super}}')
        self.visitBlock(block)
        if block.mode == 'prepend':
            self.buffer('{{block.super}}')
        self.buffer('{% endblock %}')

    def visitAssignment(self, assignment):
        self.buffer('{%% __pypugjs_set %s = %s %%}' % (assignment.name, assignment.val))

    def visitMixin(self, mixin):
        self.mixing += 1
        if not mixin.call:
            self.buffer('{%% __pypugjs_kwacro %s %s %%}' % (mixin.name, mixin.args))
            self.visitBlock(mixin.block)
            self.buffer('{% end__pypugjs_kwacro %}')
        elif mixin.block:
            raise CurrentlyNotSupported("The mixin blocks are not supported yet.")
        else:
            self.buffer('{%% __pypugjs_usekwacro %s %s %%}' % (mixin.name, mixin.args))
        self.mixing -= 1

    def visitCode(self, code):
        if code.buffer:
            val = code.val.lstrip()
            val = self.var_processor(val)
            self.buf.append('{{%s%s}}' % (val, '|force_escape' if code.escape else ''))
        else:
            self.buf.append('{%% %s %%}' % code.val)

        if code.block:
            self.visit(code.block)

            if not code.buffer:
                code_tag = code.val.strip().split(' ', 1)[0]
                if code_tag in self.auto_close_code:
                    self.buf.append('{%% end%s %%}' % code_tag)

    def visitExtends(self, node):
        path = self.format_path(node.path)
        self.buffer('{%% extends "%s" %%}' % (path))
        self.buffer('{% load pugjs %}')


    def visitInclude(self, node):
        path = self.format_path(node.path)
        if os.path.splitext(path)[-1].lower() not in ['.pug', '.jade']:
            rpath = self._getRealFilePath(path)
            if rpath:
                with open(rpath) as f:
                    self.buffer(f.read())
                return
        self.buffer('{%% include "%s" %%}' % (path))


    def attributes(self, attrs):
        return "{%% __pypugjs_attrs %s %%}" % attrs

    def compile(self):
        compiled = super(Compiler, self).compile()
        if "{% load pugjs %}" not in compiled:
            compiled = "{% load pugjs %}" + compiled
        return compiled


def decorate_templatize(func):
    def templatize(src, origin=None, charset=None):
        src = to_text(src, charset or settings.FILE_CHARSET)
        if origin.endswith(".pug"):
            html = process(
                src, compiler=Compiler,
                base_directory=os.path.basename(origin)
            )
        else:
            html = src
        return func(html, origin)

    return templatize


# fix translation for pug templates
def enable_pug_translations():
    template.templatize = decorate_templatize(template.templatize)


try:
    from django.contrib.markup.templatetags.markup import markdown

    @register_filter('markdown')
    def markdown_filter(x, y):
        return markdown(x)


except ImportError:
    pass
