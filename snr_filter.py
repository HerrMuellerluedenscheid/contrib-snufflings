import numpy as num
import math
import time
import itertools

from pyrocko.gui.snuffling import Snuffling, Param, Switch, Choice # , TextEdit
from pyrocko.gui.util import EventMarker, PhaseMarker
from pyrocko import trace
from pyrocko import cake
from pyrocko import model
from pyrocko import util
from pyrocko import orthodrome as ortho
from pyrocko.dataset import crust2x2


class SNRFilterTraces(Snuffling):

    '''
    <html>
    <body>
    <h1>Show only traces with a large SNR</h1>
    </body>
    </html>
    '''

    def setup(self):
        '''Customization of the snuffling.'''

        self.set_name('SNR filter traces')
        self.add_parameter(Param('Data Window:', 'win_length', 10., 0, 100.))
        self.add_parameter(Param('Hide below SNR', 'snr_threshold', 1., 1., 10.,
                                 low_is_none=True))
        self.add_parameter(Choice('Phase', 'phase_select', 'P', ['p', 'P']))
        self.add_parameter(Choice('Channel', 'want_channel', '*', ['*Z']))
        self.add_parameter(Switch('Dry-run', 'dry_run', False))
        self.add_parameter(Switch('Add markers', 'want_markers', True))
        self.add_parameter(Switch('Plot', 'want_plot', False))
        self.set_live_update(False)
        self.fig = None
        self._phase_cache = {}
        self._hidden = []

    def unhide(self):
        viewer = self.get_viewer()
        for pattern in self._hidden:
            viewer.remove_blacklist_pattern(pattern)
        self._hidden = []

    def hide(self, patterns):
        viewer = self.get_viewer()
        for pattern in patterns:
            viewer.add_blacklist_pattern(pattern)
        self._hidden = patterns

    def cleanup(self):
        self.unhide()
        try:
            viewer = self.get_viewer()
            viewer.release_data(self._tickets)
            viewer.remove_markers(self._markers)

        except NoViewerSet:
            pass

        self._tickets = []
        self._markers = []

    def call(self):
        '''Main work routine of the snuffling.'''
        self.cleanup()
        viewer = self.get_viewer()
        event, stations = self.get_active_event_and_stations()
        phase_def = cake.PhaseDef(self.phase_select)
        markers = []
        markers_noise = []
        win_start = -self.win_length/2.
        win_stop = self.win_length/2.
        win_noise_start = win_start - self.win_length
        win_noise_stop = win_start
        mod = cake.load_model()

        to_hide = ['.'.join(k) for k in self.get_pile().nslc_ids.keys()]

        for istation, s in enumerate(stations):
            d = ortho.distance_accurate50m(s, event) * cake.m2d
            cache_key = (d, event.depth)
            t = self._phase_cache.get(cache_key, False)
            if t is None:
                continue

            elif t is False:
                arrs = mod.arrivals(phases=[phase_def], distances=[d], zstart=event.depth)
                if len(arrs) == 0:
                    print('No arrival at station %s' % ('.'.join(s.nsl())))
                    self._phase_cache[cache_key] = None
                    continue
                t = arrs[0].t + event.time
                self._phase_cache[cache_key] = t
            markers.append(PhaseMarker(
                    tmin=t+win_start, tmax=t+win_stop,
                    nslc_ids=[s.nsl() + (self.want_channel,)],
                    phasename=self.phase_select, kind=3))

            markers_noise.append(PhaseMarker(
                    tmin=t+win_noise_start, tmax=t+win_noise_stop,
                    nslc_ids=[s.nsl() + (self.want_channel,)],
                    phasename=self.phase_select+'_noise', kind=3))
            
            markers[-1].set_selected(True)
            markers_noise[-1].set_selected(True)
            print('done %s/%s' % (istation+1, len(stations)))

        if self.want_markers:
            self.add_markers(markers)
            self.add_markers(markers_noise)

        if self.dry_run:
            return

        traces_data = []
        snr = {}

        def marker_selector(m):
            return m in markers

        def noise_marker_selector(m):
            return m in markers_noise

        chopper_mode = 'all'
        trs_d = self.chopper_selected_traces(mode=chopper_mode,
            marker_selector=marker_selector)
        trs_n = self.chopper_selected_traces(mode=chopper_mode,
            marker_selector=noise_marker_selector)

        for i, (tr_d, tr_n) in enumerate(zip(trs_d, trs_n)):
            if len(tr_d) != 1 or len(tr_n) != 1:
                print('Odd chopping... skipping')
                continue
            if viewer.highpass:
                tr_d[0].highpass(4, viewer.highpass)
                tr_n[0].highpass(4, viewer.highpass)
            if viewer.lowpass:
                tr_d[0].lowpass(4, viewer.lowpass)
                tr_n[0].lowpass(4, viewer.lowpass)

            y1 = tr_d[0].get_ydata().astype(num.float)
            y2 = tr_n[0].get_ydata().astype(num.float)
            snr['.'.join(tr_d[0].nslc_id)] = num.max(
                num.sqrt(num.sum(y1**2)/num.sum(y2**2)))

        if self.want_plot:
            if self.fig is None or self.fframe.closed is True or not self._live_update:
                self.fframe = self.pylab(get='figure_frame')
                self.fig = self.fframe.gcf()
     
            if self._live_update:
                self.fig.clf()

            ax = self.fig.add_subplot(111)

            threshold = self.snr_threshold if self.snr_threshold else 0.
            snr_values = []
            snr_keys = []
            for k in sorted(snr.keys()):
                if snr[k] > threshold:
                    snr_values.append(snr[k])
                    snr_keys.append(k)

            ypos = range(len(snr_values))
            ax.barh(ypos, snr_values, align='center', color='grey')
            ax.set_yticks(ypos)
            ax.set_yticklabels(snr_keys)

            self.fig.canvas.draw()

        if self.snr_threshold:
            for k, v in snr.items():
                if v > self.snr_threshold:
                    to_hide.remove(k)
            self.hide(to_hide)
        

def __snufflings__():
    '''Returns a list of snufflings to be exported by this module.'''
    return [SNRFilterTraces()]
