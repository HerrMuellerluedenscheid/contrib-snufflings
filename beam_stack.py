from pyrocko.snuffling import Snuffling, Param, Switch
from pyrocko.model import Station
from pyrocko import orthodrome as ortho
from pyrocko import util
import numpy as num
from collections import defaultdict

class BeamForming(Snuffling):
    '''
    <html>
    <body>
    <h1>Beam Formin</h1>

    If not reference point is defined using 'Center lat' and 'Center lon'
    calculated a geographical center by taking the average of latitudes and
    longitudes.
    
    Activating normalization will normalize traces using their standard
    deviation.
    </body>
    </html>

    '''
    def setup(self):
        self.set_name("Beam Forming")
        self.add_parameter(Param('Center lat', 'lat_c', 90., -90., 90.,
                                high_is_none=True))
        self.add_parameter(Param('Center lon', 'lon_c', 180., -180., 180.,
                                high_is_none=True))
        self.add_parameter(Param('Back azimuth', 'bazi', 0., 0., 360.))
        self.add_parameter(Param('Slowness', 'slow', 0.2, 0., 4))
        self.add_parameter(Switch('Normalize Traces', 'normalize', False))
        self.station_c = None
        self.stacked_traces = None

    def call(self):
        
        self.cleanup()
        viewer = self.get_viewer()
        if self.station_c:
            viewer.stations.pop(('', 'STK'))

        stations = self.get_stations()
 
        if not self.lat_c or not self.lon_c:
            self.lat_c, self.lon_c = self.center_lat_lon(stations)
            self.set_parameter('lat_c', self.lat_c)
            self.set_parameter('lon_c', self.lon_c)

        self.station_c = Station(lat=self.lat_c, 
                                 lon=self.lon_c, 
                                 name='Array Center', 
                                 network='',
                                 station='STK')

        viewer.add_stations([self.station_c])
        
        distances = [ortho.distance_accurate50m(self.station_c, s) for s in
                stations]
         
        azirad = self.bazi/180.*num.pi
        azis = num.array([ortho.azimuth(s, self.station_c) for s in stations])
        azis %= 360.
        azis = azis/180.*num.pi

        gammas = azis - azirad
        gammas = gammas%(2*num.pi)

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
                    stat = stats[0]
                except IndexError:
                    print 'stats ', stats
                    break
                
                i = stations.index(stat)
                gamma = gammas[i]

                d = num.cos(gamma)*distances[i]
                t_shift = d*self.slow/1000.
                tr.shift(-t_shift)
                if self.normalize:
                    tr.ydata = tr.ydata/tr.ydata.std()
                stack_trace.add(tr)

        self.add_traces(stacked.values())

    def center_lat_lon(self, stations):
        '''Calculate a mean geographical centre of the array
        using spherical earth'''

        lats = num.zeros(len(stations))
        lons = num.zeros(len(stations))
        for i,s in enumerate(stations):
            lats[i] = s.lat/180.*num.pi
            lons[i] = s.lon/180.*num.pi
        x = num.cos(lats) * num.cos(lons)
        y = num.cos(lats) * num.sin(lons)

        return (lats.mean()*180/num.pi, lons.mean()*180/num.pi)
    
def __snufflings__():
    return [ BeamForming() ]

