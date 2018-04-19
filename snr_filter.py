import numpy as num
import math
import time
import itertools
import logging

from pyrocko.gui.snuffling import Snuffling, Param, Switch, Choice # , TextEdit
from pyrocko.gui.marker import EventMarker, PhaseMarker, associate_phases_to_events
from pyrocko import trace
from pyrocko import cake
from pyrocko import model
from pyrocko import util
from pyrocko import orthodrome as ortho
from pyrocko.dataset import crust2x2


logger = logging.getLogger('XX')


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
        self.add_parameter(Choice('Phase', 'phase_select', 'picks', ['p', 'P', 'picks']))
        self.add_parameter(Choice('Method', 'method', 'power', ['power', 'peak']))
        self.add_parameter(Switch('Dry-run', 'dry_run', False))
        self.add_parameter(Switch('Add markers', 'want_markers', True))
        self.add_parameter(Switch('Plot', 'want_plot', True))
        self.add_parameter(Switch('[db]', 'db', False))
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
        stations = self.get_stations()

        if self.phase_select != 'picks':
            phase_def = cake.PhaseDef(self.phase_select)


        win_start = -self.win_length/2.
        win_stop = self.win_length/2.
        win_noise_start = win_start - self.win_length
        win_noise_stop = win_start
        mod = cake.load_model()

        to_hide = ['.'.join(k) for k in self.get_pile().nslc_ids.keys()]

        markers = self.get_selected_markers()
        associate_phases_to_events(markers)

        # TODO: cleanup
        event_markers = [m.get_event() for m in markers if isinstance(m, PhaseMarker)]
        event_markers = [EventMarker(m) for m in event_markers if m]

        if len(event_markers) == 0:
            self.fail('No event markers selected')

        if len(event_markers)>1 and self.snr_threshold:
            self.fail('SNR threshold works only on single events')

        if self.phase_select == 'picks':
            by_t0 = {}
            for m in markers:
                if isinstance(m, PhaseMarker):
                    e = m.get_event()
                    if not e:
                        continue
                    marks = by_t0.get(e.time, [])
                    marks.append(m)
                    by_t0.update({e.time: marks})

        if self.method == 'power':
            def snr_calc(y1, y2, t1, t2):
                return (num.sum(y1**2)/t1)/(num.sum(y2**2)/t2)
        elif self.method == 'peak':
            def snr_calc(y1, y2, *args):
                return num.max(y1)**2/num.max(y2)**2

        nevents = len(event_markers)
        snr = {}
        for ievent, event_marker in enumerate(event_markers):
            logger.warn("%s / %s" % (ievent+1, len(event_markers)))
            markers = []
            markers_noise = []
            event = event_marker.get_event()

            if self.phase_select == 'picks':
                ms = by_t0.get(event.time, [])

                if len(ms) == 0:
                    logger.warn('no markers for event %s' % event)
                    continue
                data = [(m.nslc_ids, m.tmin, m.tmax) for m in ms]

            else:
                data = []
                for istation, s in enumerate(stations):
                    if util.match_nsls(viewer.blacklist, s.nsl()):
                        continue
                    d = ortho.distance_accurate50m(s, event) * cake.m2d
                    cache_key = (d, event.depth)
                    t = self._phase_cache.get(cache_key, False)
                    if not t:
                        arrs = mod.arrivals(phases=[phase_def], distances=[d], zstart=event.depth)
                        if len(arrs) == 0:
                            logger.warn('No arrival at station %s' % ('.'.join(s.nsl())))
                            self._phase_cache[cache_key] = None
                            continue
                        t = arrs[0].t + event.time
                    self._phase_cache[cache_key] = t
                    if t is None:
                        logger.warn('no phase %s, %s' % (station, event))
                        continue
                    data.append(((s.nsl() + ('*',)), t, t))

            for (nslc_ids, tstart, tstop) in data:
                markers.append(
                    PhaseMarker(
                        tmin=tstart+win_start, tmax=tstop+win_stop,
                        nslc_ids=nslc_ids, phasename=self.phase_select, kind=3))

                markers_noise.append(
                    PhaseMarker(
                        tmin=tstart+win_noise_start, tmax=tstop+win_noise_stop,
                        nslc_ids=nslc_ids, phasename=self.phase_select+'_noise', kind=3))
            
            for m, mn in zip(markers, markers_noise):
                m.set_selected(True)
                mn.set_selected(True)
                m.set_event(event)
                mn.set_event(event)

            if self.want_markers:
                self.add_markers(markers)
                self.add_markers(markers_noise)

            if self.dry_run:
                continue

            def marker_selector(m):
                return m in markers

            def noise_marker_selector(m):
                return m in markers_noise

            traces_data = self.chopper_selected_traces(
                mode='all', marker_selector=marker_selector,
                keep_current_files_open=True)

            traces_noise = self.chopper_selected_traces(
                mode='all', marker_selector=noise_marker_selector,
                keep_current_files_open=True)

            for i_chunk, (trs_d, trs_n) in enumerate(zip(traces_data, traces_noise)):
                for i_trace, (tr_d, tr_n) in enumerate(zip(trs_d, trs_n)):
                    try:
                        if viewer.highpass:
                            tr_d.highpass(4, viewer.highpass)
                            tr_n.highpass(4, viewer.highpass)
                        if viewer.lowpass:
                            tr_d.lowpass(4, viewer.lowpass)
                            tr_n.lowpass(4, viewer.lowpass)
                    except ValueError as e:
                        logger.warn("Skip %s. Reason: %s" % (tr_d, e))
                        continue

                    y1 = tr_d.get_ydata().astype(num.float)
                    y2 = tr_n.get_ydata().astype(num.float)

                    t1 = tr_d.tmax - tr_d.tmin
                    t2 = tr_n.tmax - tr_n.tmin
                    if self.db:
                        snr[(event, '.'.join(tr_d.nslc_id))] = 10*num.log10(snr_calc(y1, y2, t1, t2))
                    else:
                        snr[(event, '.'.join(tr_d.nslc_id))] = snr_calc(y1, y2, t1, t2)

        if self.want_plot:
            if self.fig is None or self.fframe.closed is True or not self._live_update:
                self.fframe = self.pylab(get='figure_frame')
                self.fig = self.fframe.gcf()
     
            if self._live_update:
                self.fig.clf()

            threshold = self.snr_threshold if self.snr_threshold else 0.
            snr_values = []
            snr_keys = []
            ax = None
            if len(event_markers) == 1:
                ax = self.fig.add_subplot(111)
                for k in sorted(snr.keys()):
                    if snr[k] > threshold:
                        snr_values.append(snr[k])
                        snr_keys.append(k)

                ypos = range(len(snr_values))
                ax.barh(ypos, snr_values, align='center', color='grey')
                ax.set_yticks(ypos)
                ax.set_yticklabels(snr_keys)

            else:
                magnitudes = []
                snrs = []
                by_nslc = {}
                for k in snr.keys():
                    event, nslc = k
                    if event.moment_tensor is not None:
                        magnitudes.append(event.moment_tensor.magnitude)
                    else:
                        magnitudes.append(event.magnitude)
                    vals = by_nslc.get(nslc, [])
                    vals.append((event.magnitude, snr[k]))
                    by_nslc[nslc] = vals

                n_plots = len(by_nslc)
                ncol = int(num.sqrt(n_plots)) + 1
                nrow = (n_plots % ncol) + 2

                nrow = max(1, nrow)
                ncol = max(1, ncol)
                # ax = self.fig.add_subplot(1, n_plots, i+1)
                for i, (nslc, vals) in enumerate(by_nslc.items()):
                    ax = self.fig.add_subplot(nrow, ncol, i+1, sharey=ax)
                    ax.scatter(*num.array(vals).T, color='black', alpha=0.4)
                    ax.set_title(nslc)
                    ax.set_xlabel('magnitude')
                    ax.set_ylabel('SNR %s' % tuple(['[db]' if self.db else '']))
                    ax.set_yscale('log')

            self.fig.canvas.draw()

        if self.snr_threshold:
            for k, v in snr.items():
                if v > self.snr_threshold:
                    to_hide.remove(k)
            self.hide(to_hide)
        

def __snufflings__():
    '''Returns a list of snufflings to be exported by this module.'''
    return [SNRFilterTraces()]
