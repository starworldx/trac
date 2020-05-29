# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2020 Edgewall Software
# Copyright (C) 2004 Oliver Rutherfurd
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Daniel Lundin
#         Oliver Rutherfurd (initial implementation)
#         Nuutti Kotivuori (role support)
#
# Trac support for reStructured Text, including a custom 'trac' directive
#
# 'trac' directive code by Oliver Rutherfurd, overhauled by cboos.
#
# Inserts `reference` nodes for TracLinks into the document tree.

__docformat__ = 'reStructuredText'

try:
    from docutils import nodes
    from docutils.core import publish_parts
    from docutils.parsers import rst
    from docutils.readers import standalone
    from docutils.writers import html4css1
    from docutils import __version__
except ImportError:
    has_docutils = False
else:
    has_docutils = True

from trac.api import ISystemInfoProvider
from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer, content_to_unicode
from trac.util.html import Element, Fragment, Markup, escape, find_element
from trac.util.translation import _
from trac.wiki.api import WikiSystem
from trac.wiki.formatter import WikiProcessor, Formatter, extract_link


if has_docutils:
    # Register "trac" role handler and directive

    def trac_get_reference(env, context, rawtext, target, text):
        fulltext = target + ' ' + text if text else target
        link = extract_link(env, context, fulltext)
        uri = None
        missing = False
        if isinstance(link, (Element, Fragment)):
            linktext = Markup(link).striptags()
            # the following is a bit hackish, but it takes into account:
            #  - an eventual trailing '?' for missing wiki pages
            #  - space eventually introduced due to split_page_names option
            if linktext.rstrip('?').replace(' ', '') != target:
                text = linktext
            elt = find_element(link, 'href', 'missing')
            if elt is not None:
                uri = elt.attrib.get('href', '')
                missing = 'missing' in elt.attrib.get('class', '').split()
        else:
            uri = context.href.wiki(target)
            missing = not WikiSystem(env).has_page(target)
        if uri or missing:
            reference = nodes.reference(rawtext, text or target)
            reference['refuri'] = uri
            if missing:
                reference['classes'].append('missing')
            return reference

    def trac_directive(name, arguments, options, content, lineno,
                       content_offset, block_text, state, state_machine):
        """Inserts a `reference` node into the document for a given
        `TracLink`_, based on the content of the arguments.

        Usage::

          .. trac:: target [text]

        ``target`` may be any `TracLink`_, provided it doesn't
        embed a space character (e.g. wiki:"..." notation won't work).

        ``[text]`` is optional.  If not given, ``target`` is
        used as the reference text.

        .. _TracLink: https://trac.edgewall.org/wiki/TracLinks
        """
        if hasattr(state.inliner, 'trac'):
            env, context = state.inliner.trac
            link = arguments[0]
            if len(arguments) == 2:
                text = arguments[1]
            else:
                text = None
            reference = trac_get_reference(env, context, block_text, link, text)
            if reference:
                if isinstance(state, rst.states.SubstitutionDef):
                    return [reference]
                p = nodes.paragraph()
                p += reference
                return [p]
            # didn't find a match (invalid TracLink)
            msg = _("%(link)s is not a valid TracLink", link=arguments[0])
            # this is an user facing message, hence localized
        else:
            msg = "No trac context active while rendering"
            # this is more an internal error, not translated.
        # report a warning
        warning = state_machine.reporter.warning(
            msg, nodes.literal_block(block_text, block_text), line=lineno)
        return [warning]

    def trac_role(name, rawtext, text, lineno, inliner, options={},
                  content=[]):
        if hasattr(inliner, 'trac'):
            env, context = inliner.trac
            args = text.split(" ", 1)
            link = args[0]
            if len(args) == 2:
                text = args[1]
            else:
                text = None
            reference = trac_get_reference(env, context, rawtext, link, text)
            if reference:
                return [reference], []
            msg = _("%(link)s is not a valid TracLink", link=rawtext)
        else:
            msg = "No trac context active while rendering"
        return nodes.warning(None, nodes.literal_block(text, msg)), []

    # 1 required arg, 1 optional arg, spaces allowed in last arg
    trac_directive.arguments = (1, 1, 1)
    trac_directive.options = None
    trac_directive.content = None
    rst.directives.register_directive('trac', trac_directive)
    rst.roles.register_canonical_role('trac', trac_role)

    # Register "code-block" role handler and directive
    # (code derived from the leo plugin rst2)

    def code_formatter(env, context, language, text):
        processor = WikiProcessor(Formatter(env, context), language)
        html = processor.process(text)
        raw = nodes.raw('', html, format='html')
        return raw

    def code_block_role(name, rawtext, text, lineno, inliner, options={},
                        content=[]):
        if not hasattr(inliner, 'trac'):
            return [], []
        env, context = inliner.trac
        language = options.get('language')
        if not language:
            args = text.split(':', 1)
            language = args[0]
            if len(args) == 2:
                text = args[1]
            else:
                text = ''
        return [code_formatter(env, context, language, text)], []

    def code_block_directive(name, arguments, options, content, lineno,
                             content_offset, block_text, state, state_machine):
        """
        Create a code-block directive for docutils.

        Usage: .. code-block:: language

        If the language can be syntax highlighted it will be.
        """
        if not hasattr(state.inliner, 'trac'):
            return []
        env, context = state.inliner.trac
        language = arguments[0]
        text = '\n'.join(content)
        return [code_formatter(env, context, language, text)]

    # These are documented
    # at http://docutils.sourceforge.net/spec/howto/rst-directives.html.
    code_block_directive.arguments = (
        1,  # Number of required arguments.
        0,  # Number of optional arguments.
        0)  # True if final argument may contain whitespace.

    # A mapping from option name to conversion function.
    code_block_role.options = code_block_directive.options = {
        'language':
            rst.directives.unchanged  # Return the text argument, unchanged
    }
    code_block_directive.content = 1  # True if content is allowed.
    # Register the directive with docutils.
    rst.directives.register_directive('code-block', code_block_directive)
    rst.roles.register_local_role('code-block', code_block_role)


class ReStructuredTextRenderer(Component):
    """HTML renderer for plain text in reStructuredText format."""
    implements(IHTMLPreviewRenderer, ISystemInfoProvider)

    # ISystemInfoProvider methods

    def get_system_info(self):
        if has_docutils:
            yield 'Docutils', __version__

    # IHTMLPreviewRenderer methods

    def get_quality_ratio(self, mimetype):
        if has_docutils and \
                mimetype in ('text/x-rst', 'text/prs.fallenstein.rst'):
            return 8
        return 0

    def render(self, context, mimetype, content, filename=None, rev=None):
        # Minimize visual impact of errors
        class TracHTMLTranslator(html4css1.HTMLTranslator):
            """Specialized translator with unobtrusive error reporting
            and some extra security features.
            """

            def __init__(self, *args, **kwargs):
                self._render_unsafe_content = wikisys.render_unsafe_content
                self._safe_schemes = set(wikisys.safe_schemes)
                html4css1.HTMLTranslator.__init__(self, *args, **kwargs)

            def visit_system_message(self, node):
                paragraph = node.children.pop(0)
                message = escape(paragraph.astext()) if paragraph else ''
                backrefs = node['backrefs']
                if backrefs:
                    span = ('<span class="system-message">%s</span>' %
                            (''.join('<a href="#%s" title="%s">?</a>' %
                                     (backref, message)
                                     for backref in backrefs)))
                else:
                    span = ('<span class="system-message" title="%s">?</span>'
                            % message)
                self.body.append(span)

            def depart_system_message(self, node):
                pass

            def visit_image(self, node):
                html4css1.HTMLTranslator.visit_image(self, node)
                uri = node.attributes.get('uri')
                if not wikisys.is_safe_origin(uri, context.req):
                    self.body[-1] = self.body[-1].replace(
                        '<img ', '<img crossorigin="anonymous" ')

            def visit_reference(self, node):
                if self._is_safe_uri(node.get('refuri')):
                    html4css1.HTMLTranslator.visit_reference(self, node)

            def depart_reference(self, node):
                if self._is_safe_uri(node.get('refuri')):
                    html4css1.HTMLTranslator.depart_reference(self, node)

            def _is_safe_uri(self, uri):
                if self._render_unsafe_content or not uri:
                    return True
                else:
                    pos = uri.find(':')
                    return pos < 0 or uri[0:pos] in self._safe_schemes

        wikisys = WikiSystem(self.env)
        writer = html4css1.Writer()
        writer.translator_class = TracHTMLTranslator

        inliner = rst.states.Inliner()
        inliner.trac = (self.env, context)
        parser = rst.Parser(inliner=inliner)
        content = content_to_unicode(self.env, content, mimetype)
        # The default Reader is explicitly passed as a workaround for #11248
        parts = publish_parts(content, writer=writer, parser=parser,
                              reader=standalone.Reader(parser),
                              settings_overrides={'halt_level': 6,
                                                  'file_insertion_enabled': 0,
                                                  'raw_enabled': 0,
                                                  'warning_stream': False})
        return parts['html_body']
