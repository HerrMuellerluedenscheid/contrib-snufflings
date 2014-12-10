from pyrocko.snuffling import Snuffling, Param, Switch, PhaseMarker, Choice
from pyrocko.model import Station
from pyrocko import orthodrome as ortho
from pyrocko import util
from pyrocko import trace
import numpy as num
from collections import defaultdict

class PickStack(Snuffling):
    '''
    <html>
    <body>
    <h1>Stack Traces using picks or cross correlation</h1>

    If method is 'CC', all you have to do is to either zoom into the window so
    that you see only traces you want to stack. 
    Another option is to pick an attribute that you in each trace. Make these
    picks PhaseMarkers by pressing F1, for example. Activate all phase picks by
    pressing 'e'. <br>
    Press run. <br>
    Acitvating normalization will normalize traces using standard deviation.
    Otherwise, sum trace will be normalized with number of stacked traces. <br>
    If 'pre filter' is checked, the time lag of the cross correlation used to 
    shift traces will be deduced after having filtered all traces with the 
    low and high pass filters of the main controls. This, however, does not affect 
    the stacked traces. The filtered traces are only used to get the time shift.
    </body>
    </html>
    '''
    def setup(self):
        self.set_name("Quick Stack")
        self.add_parameter(Switch('Pre-Normalize Traces',
                                  'normalize', False))
        self.add_parameter(Choice('Alignment method', 'method', 'CC', ['CC',
                                  'phase_markers']))
        self.add_parameter(Switch('Add shifted traces', 'add_shifted', False))
        self.add_parameter(Param('cc range factor', 'cc_range', 0.2, 0.1, 1.))
        self.add_parameter(Switch('pre filter (CC)', 'prefilter', False))

    def call(self):
        
        self.cleanup()
        print '........................'
        viewer = self.get_viewer()

        if self.method=='phase_markers':
            markers = self.get_selected_markers()
            phase_markers = [m for m in markers if isinstance(m, PhaseMarker)]
            tmins = [m.tmin for m in phase_markers]
            mean_tmin = num.mean(tmins)
            tshifts = defaultdict()
            for m in phase_markers:
                tshifts[tuple(m.nslc_ids)] = m.tmin-mean_tmin

        stacked = defaultdict()
        mean_tshifts = defaultdict(list)
        num_shifts = {}
        all_tshifts = {}
        for traces in self.chopper_selected_traces(fallback=True):
            for tr in traces:
                tr = tr.copy()
                tr.ydata = tr.ydata.astype(num.float64)
                tr.ydata -= tr.ydata.mean(dtype=num.float64)
                try:
                    stack_trace = stacked[tr.channel]
                except KeyError:
                    stack_trace = tr.copy(data=True)
                    stack_trace.set_ydata(num.zeros(len(stack_trace.get_ydata())))
                    stack_trace.set_codes(network='',
                                          station='STK',
                                          location='',
                                          channel=tr.channel)

                    stacked[tr.channel] = stack_trace
                    num_shifts[tr.channel] = 0
                
                ydata = tr.get_ydata()
                if self.method=='phase_markers':
                    for ks, v in tshifts.items():
                        for k in ks:
                            if util.match_nslc('.'.join(k), tr.nslc_id):
                                tr.shift(-tshifts[ks])
                                print 'trace: %s tshift: %1.6f' % \
                                    ('.'.join(tr.nslc_id), -tshifts[ks])
                                break
                
                elif self.method=='CC':
                    if all(ydata==0.):
                        continue
                    else:
                        tchop = (tr.tmax-tr.tmin)*self.cc_range/2.
                        tr.chop(tmin=tr.tmin+tchop, tmax=tr.tmax-tchop)
                        tr_c = tr.copy()
                        if self.prefilter:
                            tr_c.highpass(4, viewer.highpass)
                            tr_c.lowpass(4, viewer.lowpass)

                        c = trace.correlate(stack_trace, tr_c,
                                            normalization=self.normalize)
                        t, coef = c.max()

                        tr.shift(-t)
                        num_shifts[tr.channel] += 1
                        mean_tshifts[tr.channel].append(-t)
                        all_tshifts[tr] = -t
                
                if self.normalize:
                    tr.set_ydata(ydata/ydata.std())
                
                if self.add_shifted:
                    tr.set_station('%s_s' % tr.station)
                    self.add_trace(tr)

                stack_trace.add(tr)

        for tr, shift in all_tshifts.items():
            _this_shift_mean = num.mean(mean_tshifts[tr.channel])
            print 'trace: %s tshift: %1.3f' % \
                ('.'.join(tr.nslc_id), shift-_this_shift_mean)

        for ch, tr in stacked.items():
            if not self.normalize:
                tr.set_ydata(tr.get_ydata()/num_shifts[ch])

            tr.shift(-1*num.mean(mean_tshifts[tr.channel]))
        self.add_traces(stacked.values())

    
def __snufflings__():
    return [ PickStack() ]

