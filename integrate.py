from pyrocko import pile, trace, util, io
import sys, os, math, time
import numpy as num
from pyrocko.snuffling import Param, Snuffling, Switch, Choice
from pyrocko import trace
import scipy.signal as S
import scipy.stats as SS
import  scipy.signal.filter_design as F

from scipy import signal


class Integrate(Snuffling):

    '''
    ''' 
    def setup(self):    
        '''Customization of Snuffling.'''

        self.set_name('Integrate')
        self.set_force_panel(True)
        self.add_parameter(Param('fade','tfrac', 0.01, 0., 0.1))
        #self.add_parameter(Param('highpass','hp', 0., 0., 100, low_is_none=True))
        #self.add_parameter(Param('lowpass','lp', 200., 0., 200, high_is_none=True))
        self.add_parameter(Param('highpass','hp', 0., 0., 20))
        self.add_parameter(Param('lowpass','lp', 20., 0., 20))
        self.set_have_post_process_hook(True)
        self.order = 1
    def call(self):
        pass

    def integrate_trapezoidal(self, tr):
        if self.lp and self.lp*2.<1./tr.deltat:
            tr.lowpass(self.order, self.lp)
        if self.hp and self.hp*2.<1./tr.deltat:
            tr.highpass(self.order, self.hp)
        tr.taper(self.taperer)
        xdata = tr.get_xdata()
        ydata = tr.get_ydata()

        tr.set_ydata(num.cumsum((xdata[1:]-xdata[:-1])*(ydata[:-1]+ydata[1:])/2.))
        tr.tmin += tr.deltat*0.5
        return tr

    def integrate(self, tr):
        return tr.transfer(tfade=self.tfrac*(tr.tmax-tr.tmin),
                    freqlimits=(self.hp/2., self.hp, self.lp, self.lp*1.6),
                    transfer_function=self.integrationresponse)

    def post_process_hook(self, traces):
        self.integrationresponse = trace.IntegrationResponse(n=self.order)
        traces = map(self.integrate, traces)
        return traces

def __snufflings__():

    return [ Integrate()]

