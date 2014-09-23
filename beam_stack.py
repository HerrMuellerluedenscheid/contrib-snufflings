from pyrocko.snuffling import Snuffling, Param, Switch
from pyrocko.model import Station
from pyrocko import orthodrome as ortho
from pyrocko import util
import numpy as num
from collections import defaultdict

class BeamForming(Snuffling):
    '''
    TODO:
    Consider differing sampling rates!
    Pre filter 
    Use geographical array center
    '''
    def setup(self):
        self.set_name("Beam Forming")
        self.add_parameter(Param('Center lat', 'lat_c', 90., -90., 90.,
                                high_is_none=True))
        self.add_parameter(Param('Center lon', 'lon_c', 180., -180., 180.,
                                high_is_none=True))
        self.add_parameter(Param('Back azimuth', 'bazi', 0., 0., 360.))
        self.add_parameter(Param('Slowness', 'slow', 0.2, 0., 8))
        self.add_parameter(Switch('Normalize Traces(not implemented)',
            'normalize', False))
        self.add_parameter(Switch('Pre-filter with main filters',
            'prefilter', True))

    def call(self):
        
        self.cleanup()
        print self.lat_c
        print self.lon_c

        try:
            event, stations = self.get_active_event_and_stations()
        except:
            raise
 
        if not self.lat_c and not self.lon_c:
            epi_distances = [ortho.distance_accurate50m(event, s) for s in stations]
            closest_station = stations[epi_distances.index(min(epi_distances))]
            self.lat_c = closest_station.lat
            self.lon_c = closest_station.lon
        else:
            closest_station = Station(lat=self.lat_c, lon=self.lon_c)
        
        distances = [ortho.distance_accurate50m(closest_station, s) for s in
                stations]
        print ' closest station lat lon: ', closest_station.lat
        print ' closest station lat lon: ', closest_station.lon
         
        azirad = self.bazi/180.*num.pi
        print 'azimuth rad ', azirad

        self.bazi = 180.*num.pi
        azis = num.array([ortho.azimuth(s, closest_station) for s in stations])
        print 'pure azis', azis
        azis %= 360.
        azis = azis/180.*num.pi
        print 'worked azis', azis

        gammas = azis - azirad
        gammas = gammas%(2*num.pi)
        print 'gammas ', gammas

        # Iterate over all trace selections:
        stacked = defaultdict()
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
                nslc_id = tr.nslc_id

                try:
                    stats = filter(lambda x: util.match_nslc('%s.%s.%s.*'%x.nsl(),
                                                        nslc_id), stations)
                    print stats
                    stat = stats[0]
                except IndexError:
                    print 'EMPTY? maybe no station infos'
                    print 'stats ', stat
                    break
                
                i = stations.index(stat)
                gamma = gammas[i]

                d = num.cos(gamma)*distances[i]
                t_shift = d*self.slow/1000.
                print 'd' ,d
                print 'tshift', t_shift
                tr.shift(-t_shift)
                stack_trace.add(tr)

        self.add_traces(stacked.values())

    
def __snufflings__():
    return [ BeamForming() ]

