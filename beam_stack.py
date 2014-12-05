from mpl_toolkits.mplot3d import Axes3D

from pyrocko.snuffling import Snuffling, Param, Switch
from pyrocko.model import Station
from pyrocko import orthodrome as ortho
from pyrocko import util
import numpy as num
from collections import defaultdict
import matplotlib.pyplot as plt

def to_cartesian(items):
    lats = num.zeros(len(items))
    lons = num.zeros(len(items))
    depths = num.zeros(len(items))
    elevations = num.zeros(len(items))
    r = 6371000.785
    res = defaultdict()

    for i, item in enumerate(items):
        lat = item.lat/180.*num.pi
        lon = item.lon/180.*num.pi
        depth = item.depth
        elevation = item.elevation
        x = r*num.cos(lat)*num.sin(lon)
        y = r*num.cos(lat)*num.cos(lon)
        dz = elevation - depth
        z = r+dz*num.sin(lat)
        res[item] = (x,y,z)
    return res


class BeamForming(Snuffling):
    '''
    <html>
    <body>
    <h1>Beam Forming</h1>

    If not reference point is defined using 'Center lat' and 'Center lon' sliders
    geographical center is calculated by taking the average of latitudes and
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
        self.add_parameter(Param('horizontal slowness [s/km]', 'slow', 0.1, 0., 1))
        self.add_parameter(Switch('Normalize Traces', 'normalize', False))
        self.add_trigger('plot', self.plot)
        self.station_c = None
        self.z_c = None
        self.stacked_traces = None

    def call(self):
        
        self.cleanup()
        viewer = self.get_viewer()
        if self.station_c:
            viewer.stations.pop(('', 'STK'))

        stations = self.get_stations()
 
        if not self.lat_c or not self.lon_c or not self.z_c:
            self.lat_c, self.lon_c, self.z_c = self.center_lat_lon(stations)
            self.set_parameter('lat_c', self.lat_c)
            self.set_parameter('lon_c', self.lon_c)

        self.station_c = Station(lat=self.lat_c, 
                                 lon=self.lon_c, 
                                 elevation=self.z_c, 
                                 depth=0.,
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
        channels = set()
        stacked = defaultdict()
        self.t_shifts = {}
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
                    channels.add(tr.channel)
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
                print 'shifting trace ', tr, 
                print 'by %s seconds'%(-1*t_shift)
                stat = viewer.get_station(tr.nslc_id[:2])
                self.t_shifts[stat] = t_shift
                if self.normalize:
                    tr.ydata = tr.ydata/tr.ydata.std()
                stack_trace.add(tr)

        self.add_traces(stacked.values())

    def center_lat_lon(self, stations):
        '''Calculate a mean geographical centre of the array
        using spherical earth'''

        lats = num.zeros(len(stations))
        lons = num.zeros(len(stations))
        elevations = num.zeros(len(stations))
        depths = num.zeros(len(stations))
        for i,s in enumerate(stations):
            lats[i] = s.lat/180.*num.pi
            lons[i] = s.lon/180.*num.pi
            depths[i] = s.depth
            elevations[i] = s.elevation
        
        x = num.cos(lats) * num.cos(lons)
        y = num.cos(lats) * num.sin(lons)
        z = num.mean(elevations-depths)
        return (lats.mean()*180/num.pi, lons.mean()*180/num.pi, z)

    def plot(self):
        stations = self.get_stations()
        res = to_cartesian(stations)
        x = num.zeros(len(res))
        y = num.zeros(len(res))
        z = num.zeros(len(res))
        sizes = num.zeros(len(res))
        stat_labels = []
        i = 0
        for s, xyz in res.items():
            x[i] = xyz[1]
            y[i] = xyz[0]
            z[i] = xyz[2]
            #needs improvement: could be more than one trace per station
            # TODO ANDERS    SSSSSS
            try:
                sizes[i] = self.t_shifts[s]
                stat_labels.append('%s\n%1.2f'%(s.nsl_string(), sizes[i]))
            except KeyError:
                continue
            finally:
                i+=1

        x/=1000. 
        y/=1000. 
        z/=1000. 
        xmax = x.max()
        xmin = x.min()
        ymax = y.max()
        ymin = y.min()

        x_range = num.abs(xmax-xmin)
        y_range = num.abs(ymax-ymin)

        max_range = num.max([x_range, y_range])

        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        ax.scatter(x,y,z, c=sizes, s=40)
        for i, lab in enumerate(stat_labels):
            ax.text(x[i],y[i],z[i], lab, size=9)
        ax.set_xlim([x.mean()-max_range*0.55, x.mean()+max_range*0.55])
        ax.set_ylim([y.mean()-max_range*0.55, y.mean()+max_range*0.55])
        ax.set_zlim([z.mean()-max_range*0.2, z.mean()+max_range*0.2])
        ax.set_xlabel("N-S")
        ax.set_ylabel("E-W")
        plt.show()

def __snufflings__():
    return [ BeamForming() ]

