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


__all__ = ['redis_call', 'TrackingRedisMixin', 'TrackingRedis',
           'StrictTrackingRedis', 'RedisPanel']


redis_call = Signal(providing_args=['function', 'args', 'trace',
                                    'start', 'stop', 'duration',
                                    'return'])


class TrackingRedisMixin(object):
    def execute_command(self, func_name, *args, **kwargs):
        debug_config = getattr(settings, 'DEBUG_TOOLBAR_CONFIG', {})
        enable_stack = debug_config.get('ENABLE_STACKTRACES', True)

        trace =  enable_stack and tidy_stacktrace(reversed(get_stack()))[:-2] or []

        call = { 'function': func_name,
                 'args': map(unicode, args + tuple(kwargs.values())),
                 'trace': trace }

        try:
            call['start'] = time.time()
            ret = super(TrackingRedisMixin, self).execute_command(func_name,
                    *args, **kwargs)
        finally:
            call['stop'] = time.time()
            call['duration'] = (call['stop'] - call['start']) * 1000
            call['return'] = unicode(ret)

            redis_call.send_robust(sender=self, **call)

        return ret


class TrackingRedis(TrackingRedisMixin, Redis):
    pass

class StrictTrackingRedis(TrackingRedisMixin, StrictRedis):
    pass


class RedisPanel(DebugPanel):
    name = 'Redis'
    has_content = True

    def __init__(self, *args, **kwargs):
        super(RedisPanel, self).__init__(*args, **kwargs)
        self.calls = []
        redis_call.connect(self._add_call)

    def _add_call(self, sender, **kw):
        kw['trace'] = render_stacktrace(kw['trace'])
        self.calls.append(kw)

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
        for call in self.calls:
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
{% for command, count in commands.iteritems %}
<p class="fieldset">
    <label>
        <input class="filter" value=".{{ command }}" type="checkbox">
        <span class="legend">{{ command }}:</span>
        <span>{{ count }}</span>
    </label>
</p>
{% endfor %}

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
        {% for call in calls %}

        <tr class="{{ call.function }}">
            <td>{{ call.duration }} ms</td>
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
    </tbody>
</table>
<script type="text/javascript">
    $('.filter').change(function () {
      $('.filter').each(function () {
        var $this = $(this)
          , $target = $($this.val())
        if ($this.attr('checked')) {
            $target.show()
        }
        else {
            $target.hide()
        }
      })
    })
</script>
"""
