import os
import time
import operator

from django.conf import settings
from django.template import Template, Context
from django.dispatch import Signal
from django.utils.translation import ugettext_lazy as _, ungettext
from django.utils.html import escape
from django.utils.safestring import mark_safe

from debug_toolbar.utils import get_stack, tidy_stacktrace
from debug_toolbar.panels import DebugPanel
from redis import Redis, StrictRedis
from redis.client import BasePipeline


__all__ = ['redis_call', 'TrackingRedisMixin', 'TrackingRedis',
           'StrictTrackingRedis', 'BaseTrackingPipeline', 'RedisPanel',
           'TrackingPipelineMixin', 'TrackingPipeline',
           'StrictTrackingPipeline']


redis_call = Signal(providing_args=['duration', 'calls'])


class TrackingRedisMixin(object):
    def execute_command(self, func_name, *args, **kwargs):
        debug_config = getattr(settings, 'DEBUG_TOOLBAR_CONFIG', {})
        enable_stack = debug_config.get('ENABLE_STACKTRACES', True)

        trace =  enable_stack and tidy_stacktrace(reversed(get_stack()))[:-2] or []

        call = { 'function': func_name,
                 'args': map(unicode, args + tuple(kwargs.values())),
                 'trace': trace }

        try:
            start = time.time()
            ret = super(TrackingRedisMixin, self).execute_command(func_name,
                    *args, **kwargs)
            call['return'] = unicode(ret)
        finally:
            stop = time.time()
            duration = (stop - start) * 1000

            redis_call.send_robust(sender=self, duration=duration, calls=(call,))

        return ret

class BaseTrackingPipeline(BasePipeline):
    def execute(self, *args, **kw):
        debug_config = getattr(settings, 'DEBUG_TOOLBAR_CONFIG', {})
        enable_stack = debug_config.get('ENABLE_STACKTRACES', True)

        trace =  enable_stack and tidy_stacktrace(reversed(get_stack()))[:-2] or []

        transaction = {'calls': []}

        for arguments, options in self.command_stack:
            transaction['calls'].append({'function': arguments[0],
                                         'args': map(unicode, tuple(arguments[1:]) + tuple(options.values())),
                                         'trace': trace})

        try:
            start = time.time()
            ret = super(BaseTrackingPipeline, self).execute(*args, **kw)

            for i, call in enumerate(transaction['calls']):
                call['return'] = unicode(ret[i])
        finally:
            stop = time.time()
            transaction['duration'] = (stop - start) * 1000

            redis_call.send_robust(sender=self, **transaction)

        return ret


class TrackingRedis(TrackingRedisMixin, Redis):
    def pipeline(self, transaction=False, shard_hint=None):
        return TrackingPipeline(
                self.connection_pool,
                self.response_callbacks,
                transaction,
                shard_hint,
            )

class StrictTrackingRedis(TrackingRedisMixin, StrictRedis):
    def pipeline(self, transaction=False, shard_hint=None):
        return StrictTrackingPipeline(
                self.connection_pool,
                self.response_callbacks,
                transaction,
                shard_hint,
            )

class TrackingPipeline(BaseTrackingPipeline, TrackingRedis):
    pass

class StrictTrackingPipeline(BaseTrackingPipeline, StrictTrackingRedis):
    pass


class RedisPanel(DebugPanel):
    name = 'Redis'
    has_content = True

    def __init__(self, *args, **kwargs):
        super(RedisPanel, self).__init__(*args, **kwargs)
        self.calls = []
        redis_call.connect(self._add_call)

    def _add_call(self, sender, duration, calls, **kw):
        for call in calls:
            call['trace'] = render_stacktrace(call['trace'])
        self.calls.append({'duration': duration, 'calls': calls})

    def nav_title(self):
        return _("Redis")
    title = nav_title

    def nav_subtitle(self):
        calls = len(self.calls)
        duration = sum(map(operator.itemgetter('duration'), self.calls))

        return ungettext('%(calls)d call in %(duration).2fms',
                         '%(calls)d calls in %(duration).2fms',
                         calls) % {'calls': calls, 'duration': duration}

    def url(self):
        return ''

    def content(self):
        context = {'calls': self.calls, 'commands': {}}
        for tr in self.calls:
            for call in tr['calls']:
                context['commands'][call['function']] = \
                        context['commands'].get(call['function'], 0) + 1
        return Template(template).render(Context(context))


def render_stacktrace(trace):
    stacktrace = []
    for frame in trace:
        params = map(escape, frame[0].rsplit(os.path.sep, 1) + list(frame[1:]))
        try:
            stacktrace.append(u'<span class="path">{0}/</span><span class="file">{1}</span> in <span class="func">{3}</span>(<span class="lineno">{2}</span>)\n  <span class="code">{4}</span>'.format(*params))
        except IndexError:
            # This frame doesn't have the expected format, so skip it and move on to the next one
            continue
    return mark_safe('\n'.join(stacktrace))


template = """
{% load i18n %}
<h4>{% trans "Calls" %}</h4>
<table>
    <thead>
        <tr>
            <th>{% trans "Command" %}</th>
            <th>{% trans "Count" %}</th>
        </tr>
    </thead>
    <tbody>
    {% for command, count in commands.iteritems %}
        <tr>
            <td>{{ command }}</td>
            <td>{{ count }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>

<table>
    <thead>
        <tr>
            <th>{% trans "Duration" %}</th>
            <th>{% trans "Call" %}</th>
            <th>{% trans "Args" %}</th>
            <th>{% trans "Result" %}</th>
        </tr>
    </thead>

    <tbody>
        {% for tr in calls %}
        {% for call in tr.calls %}
        <tr>
            <td>{% if forloop.first %}{{ tr.duration }} ms{% endif %}</td>
            <td>{{ call.function }}</td>
            <td>{{ call.args }}</td>
            <td>{{ call.return }}</td>
        </tr>

        {% if call.trace %}
            <tr class="{{ call.function }}">
                <td colspan="4">
                    <pre class="stack">{{ call.trace }}</pre>
                </td>
            </tr>
        {% endif %}

        {% endfor %}
        {% endfor %}
    </tbody>
</table>
"""
