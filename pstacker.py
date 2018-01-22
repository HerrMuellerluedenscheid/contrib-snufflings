import numpy as num
import math
from collections import defaultdict
import hashlib

from pyrocko.gui.snuffling import Snuffling, Param, Switch, Choice
from pyrocko.gui.util import EventMarker
from pyrocko import trace
from pyrocko import cake
from pyrocko import model
from pyrocko import util
from pyrocko import orthodrome as ortho
from pyrocko.dataset import crust2x2


class Pstacker(Snuffling):

    '''
    <html>
    <body>
    <h1>Plot PSD (Power Spectral Density)</h1>

    Visible or selected data is cut into windows of 2 x 'Window length',
    tapered with a Hanning taper, FFTed, sqared, normalized and gathered by
    mean or median and percentiles.

    </body>
    </html>
    '''

    def setup(self):
        '''Customization of the snuffling.'''

        self.set_name('WoddyWoodStacker')
        self.add_parameter(
            Param('Window + [s]:', 'win_pos', 10, 0, 100.,
                  high_is_none=True))
        self.add_parameter(
            Param('Window - [s]:', 'win_neg', 0., 1, 100.,
                  high_is_none=True))
        self.add_parameter(
            Param('Highpass', 'highpass', 0.7, 0., 100.,
                  low_is_none=True))
        self.add_parameter(
            Param('Lowpass', 'lowpass', 9., 0.001, 100.,
                  high_is_none=True))
        self.add_parameter(
            Param('STALTA short', 'tshort', 0.5, 0., 5.,
                  high_is_none=True))
        self.add_parameter(
            Param('STALTA long (ratio)', 'tlong', 3., 0., 5.,
                  high_is_none=True))
        self.add_parameter(
            Param('Depth [km]', 'depth', 10., 0., 30.,
                  high_is_none=True))
        self.add_parameter(
            Choice('Handle sampling rates', 'handle_dt', 'Interpolate',
                   ['Downsample', 'Interpolate']))
        self.add_parameter(
            Choice('Process', 'process', 'abs',
                   ['abs', 'none', 'sta/lta',
                    'envelope']))
        self.add_parameter(
            Switch('Strict', 'strict', True))
        self.add_parameter(
            Switch('Normalize', 'normalize', True))
        self.add_parameter(
            Switch('Calculate Phases', 'phases', False))
        self.add_parameter(
            Switch('Square', 'square', True))
        self.set_live_update(False)
        self.fig = None
        self.phase_cache = {}

    def call(self):
        '''Main work routine of the snuffling.'''

        markers = self.get_selected_markers()

        shifts = []
        trs = []
        pile = self.get_pile()
        viewer = self.get_viewer()
        snippets = []
        for m in markers:
            if isinstance(m, EventMarker):
                continue
            if self.strict:
                selector = lambda tr: m.match_nslc(tr.nslc_id)
            else:
                selector = lambda tr: m.match_nsl(tr.nslc_id[:3])
            for traces in pile.chopper(tmin=m.tmin-self.win_neg,
                                       tmax=m.tmax+self.win_pos,
                                       trace_selector=selector,
                                       want_incomplete=True):
                for tr in traces:
                    tr = tr.copy(data=True)
                    shift = -m.tmin
                    tr.shift(shift)
                    shifts.append(shift)
                    snippets.append(tr)

        dts = [tr.deltat for tr in snippets]
        if len(dts) == 0:
            self.fail('No traces selected')
        if self.handle_dt == 'Downsample':
            deltat = max(dts)
        else:
            deltat = min(dts)
        tmax_stack = max([tr.tmax for tr in snippets])

        new_datalen = int(round((self.win_neg + self.win_pos) / deltat))
        ydata = num.zeros(new_datalen)

        taper = trace.CosFader(xfrac=0.1)
        by_nslc = {}
        for tr in snippets:
            # use sta lta, envelope, etc.
            if self.highpass:
                tr.highpass(4, self.highpass)

            if self.lowpass:
                tr.lowpass(4, self.lowpass)

            if self.process == 'envelope':
                tr.envelope()

            if self.process == 'sta/lta':
                tr.sta_lta_centered(self.tshort, self.tshort * self.tlong)
            
            if self.process == 'abs':
                ydata = tr.get_ydata()
                tr.set_ydata(num.abs(ydata))

            if self.normalize:
                ydata = tr.get_ydata()
                ydata = ydata / num.max(ydata)
                tr.set_ydata(ydata)

            if self.square:
                ydata = tr.get_ydata()
                ydata = ydata**2
                tr.set_ydata(ydata)

            tr.taper(taper)
            by_nslc[tr.nslc_id] = tr

        stack = trace.Trace(network='XX', station='XXX',
                            tmin=-self.win_neg, tmax=tmax_stack,
                            deltat=deltat, ydata=ydata)
        for nslc_id, tr in by_nslc.items():
            stack.add(tr)

        if self.fig is None or self.fframe.closed is True or not self._live_update:
            self.fframe = self.pylab(get='figure_frame')
            self.fig = self.fframe.gcf()
 
        if self._live_update:
            self.fig.clf()

        ax = self.fig.add_subplot(131)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        for tr in snippets:
            ax.plot(tr.get_xdata(), tr.get_ydata(), alpha=0.5,# color='grey',
                    label='.'.join(tr.nslc_id))
        d = num.ones(stack.data_len())
        taper(d, 0, deltat)
        ax.plot(stack.get_xdata(), d, color='grey', alpha=0.3, label='taper')
        ax.legend()
        ax = self.fig.add_subplot(132)

        ax.plot(stack.get_xdata(), stack.get_ydata(), color='black')
        phases_ordered = defaultdict(list)
        if self.phases:
            distances = []
            last_distance = None
            distance_to_station = {}
            depth = int(self.depth) * 1000.
            phase_strings = ['P', 'pP', 'sP']
            colors = dict(zip(phase_strings, 'rgby'))
            phase_key = '.'.join(phase_strings)
            phase_defs = [cake.PhaseDef(x) for x in phase_strings]
            event, _ = self.get_active_event_and_stations()
            stations = self.get_stations()
            if event is None:
                print('No active event. Using AK135 model')
                earth_model = cake.load_model()
            else:
                earth_model = cake.load_model(crust2_profile=(event.lat, event.lon))

            cache_key = str(depth) + phase_key
            for m in markers:
                if isinstance(m, EventMarker):
                    continue
                for station in stations:
                    if m.match_nsl(station.nsl()):
                        break
                else:
                    print('No station found for marker: %s' % m)
                    continue

                distance = ortho.distance_accurate50m(
                    station.lat, station.lon, event.lat, event.lon)

                distances.append(distance*cake.m2d)
                cache_key += str(distance)
                distance_to_station[distance*cake.m2d] = station

            phases = self.phase_cache.get(cache_key, False)
            if not phases:
                phases = earth_model.arrivals(
                    distances=distances, phases=phase_defs, zstart=depth)
                self.phase_cache[cache_key] = phases

            for p in phases:
                if p.x != last_distance:
                    first = p.t
                    last_distance = p.x
                phases_ordered[p.given_phase().definition()].append(p.t - first)

            ax.set_title('depth = %s km' % depth)

        for phase_name, phases in phases_ordered.items():
            for t in phases:
                ax.axvline(t, label=phase_name, color=colors[phase_name])

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.legend()
        ax.set_xlim(-self.win_neg, self.win_pos)

        if self.highpass:
            tmax_stack = 1./self.highpass
        else:
            tmax_stack = 1.
        if self.phases:

            stacks = []
            ztest = num.arange(1, 30, 2) * 1000.
            for z in ztest[::-1]:
                ydata = num.zeros(new_datalen)

                stack = trace.Trace(network='', station='Z%i'%z,
                    tmin=0, tmax=tmax_stack, #tmax=tmax_stack,
                    deltat=deltat, ydata=ydata)
                # print('%i %i' % (z, max(ztest)))
                phases = earth_model.arrivals(
                    distances=distances, phases=phase_defs, zstart=z)
                # print(phases)
                last_distance = None
                for p in phases:
                    if p.x != last_distance:
                        first = p.t
                        last_distance = p.x
                    # print(p)
                    station = distance_to_station[p.x]
                    for tr in snippets:
                        if util.match_nslc(".".join(station.nsl()) + '*', tr.nslc_id):
                            tr = tr.copy(data=True)
                            tr.shift(-(p.t-first))
                            # print('depth', z, 'trace', tr, 'stack', stack, 'shift', -(p.t-first))
                            # print('/' * 10)
                            self.add_trace(tr)

                            stack.add(tr)

                stacks.append((z, stack))

            for (depth, stack) in stacks:
                ax = self.fig.add_subplot(133)
                #ax.plot(depth, stack.max()[1], 'o', color='black')
                ax.plot(depth, num.sum(stack.get_ydata()), 'o', color='black')
                self.add_trace(stack)

        self.fig.canvas.draw()
        

def __snufflings__():
    '''Returns a list of snufflings to be exported by this module.'''
    return [Pstacker()]
