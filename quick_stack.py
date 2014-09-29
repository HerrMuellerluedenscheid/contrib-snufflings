from pyrocko.snuffling import Snuffling, Param, Switch, PhaseMarker, Choice
from pyrocko.model import Station
from pyrocko import orthodrome as ortho
from pyrocko import util
from pyrocko import trace
import numpy as num
from collections import defaultdict

class PickStack(Snuffling):
    '''Stack Traces

    If method is 'CC', all you have to do is to either zoom into the window so
    that you see only traces you want to stack. 
    Another option is to pick an attribute that you in each trace. Make these
    picks PhaseMarkers by pressing F1, for example. Activate all phase picks by
    pressing 'e'. 
    Press run. 
    '''
    def setup(self):
        self.set_name("Quick Stack")
        self.add_parameter(Switch('Pre-Normalize Traces(not implemented)',
            'normalize', False))
        self.add_parameter(Switch('Pre-filter with main filters',
            'prefilter', True))
        self.add_parameter(Choice('Alignment method', 'method', 'CC', ['CC',
            'phase_markers']))

    def call(self):
        
        self.cleanup()
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
        for traces in self.chopper_selected_traces(fallback=True):
            for tr in traces:
                tr = tr.copy()
                if self.prefilter:
                    if not viewer.lowpass:
                        self.fail('Highpass and lowpass in viewer must be set!')
                    tr.lowpass(4, viewer.lowpass)
                    tr.highpass(4, viewer.highpass)

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
                
                ydata = tr.get_ydata()
                if self.method=='phase_markers':
                    for ks, v in tshifts.items():
                        for k in ks:
                            if util.match_nslc('.'.join(k), tr.nslc_id):
                                tr.shift(-tshifts[ks])
                                break
                elif self.method=='CC':
                    if all(ydata==0.):
                        continue
                    else:
                        c = trace.correlate(stack_trace, tr,
                                normalization=self.normalize)
                        t, coef = c.max()
                        tr.shift(-t)
                
                if self.normalize:
                    tr.set_ydata(ydata/ydata.max())

                stack_trace.add(tr)

        self.add_traces(stacked.values())

    
def __snufflings__():
    return [ PickStack() ]

