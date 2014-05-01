import glob
import os, time, urllib2, logging
from collections import defaultdict
from pyrocko import pile, trace, iris_ws 
from pyrocko.snuffling import Param, Snuffling, Switch, Choice

pjoin = os.path.join

logger = logging.getLogger('pyrocko.snufflings.iris_data')
logger.setLevel(logging.INFO)

class RestituteIrisData(Snuffling):
    """
    Restitute Seismic Traces
    """

    def setup(self):    
        '''Customization of the snuffling.'''
        
        self.set_name('Restitute Iris Data')
        self.add_parameter(Param('BHE/BHN 1st. freq limit', 'BH1', 
            0.01, 0.0001,  100.))
        self.add_parameter(Param('BHE/BHN 2nd. freq limit', 'BH2', 
            0.02, 0.0001,  100.))
        self.add_parameter(Param('BHE/BHN 3rd. freq limit', 'BH3', 
            20., 0.0001,  100.))
        self.add_parameter(Param('BHE/BHN 4th. freq limit', 'BH4', 
            40., 0.0001,  100.))
        #self.add_parameter(Param('BHZ 1st. freq limit', 'BHZ1', 0.0001, 0.01, 100.))
        #self.add_parameter(Param('BHZ 2nd. freq limit', 'BHZ2', 0.0002, 0.01, 100.))
        #self.add_parameter(Param('BHZ 3rd. freq limit', 'BHZ3', 20., 0.0001, 100.))
        #self.add_parameter(Param('BHZ 4th. freq limit', 'BHZ4', 40., 0.0001, 100.))
        self.add_parameter(Param('Fade Duration [s]', 'tfade', 10., 0., 240.))
        self.add_parameter(Switch('Keep originals', 'keep_origs', True))
        self.add_parameter(Choice('Type', 'rest_type', 'displacement', 
                                         ['displacement', 'velocity']))
        self.add_trigger('Replace Originals', self.replace)
        self.add_trigger('Open Resp Dir', self.load_resps)
        self.add_trigger('Save Resp Files', self.save_resps)
        self.set_live_update(False)
        self.resp_files = defaultdict()

    def call(self):
        '''Main work routine of the snuffling.'''
        
        self.cleanup()

        #flimts = {'BHZ':[self.BHZ1, self.BHZ2, self.BHZ3, self.BHZ4],
        #       'BHE':[self.BH1, self.BH2, self.BH3, self.BH4] ,
        #       'BHN':[self.BH1, self.BH2, self.BH3, self.BH4] }
        #flimts = {'BHZ':[self.BHZ1, self.BHZ2, self.BHZ3, self.BHZ4],
        #       'BHE':[self.BH1, self.BH2, self.BH3, self.BH4] ,
        #       'BHN':[self.BH1, self.BH2, self.BH3, self.BH4] }

        view = self.get_viewer()
        pile = self.get_pile()
        
        resp_req = defaultdict()
        dir = self.tempdir()

        for tr in pile.iter_traces():
            if tr.nslc_id in self.resp_files.keys():
                continue
            try:
                resp_req[tr.nslc_id] = iris_ws.ws_resp(network=tr.network,
                                                station=tr.station,
                                                location=tr.location,
                                                channel=tr.channel,
                                                tmin=tr.tmin,
                                                tmax=tr.tmax)
            except:
                raise


        logger.info('writing to tmp dir: %s'% dir)
        i = 1
        for id, req in resp_req.items():
            logger.info('requesting %s of %s'% (i, len(resp_req.keys())))
            fn = pjoin(dir,'%s.%s.%s.%s.resp'% id)
            f = open(fn, 'w')
            f.write(req.read())
            f.close()
            self.resp_files[id] = fn
         
        self.restituted = []
        self.originals = []
        for tr in pile.iter_traces(load_data=True):
            if self.keep_origs:
                self.originals.append(tr)
                tr = tr.copy(data=True)

            inveval = trace.InverseEvalresp(self.resp_files[tr.nslc_id],
                                            tr,
                                            target=self.rest_type[:3])

            fmin = 0.005
            fmax = 1.0

            tr = tr.transfer(tfade=1./fmin, #self.tfade,
                             freqlimits=(fmin/2., fmin, fmax, fmax*1.5),
                             transfer_function=inveval)


            if self.keep_origs:
                tr.network= 'rst'+tr.network

            self.restituted.append(tr)

        if self.keep_origs:
            self.add_traces(self.restituted)


    def replace(self):
        """
        Replace original traces within the pile with restituted ones.
        """
        pile = self.get_pile()
        map(pile.remove, self.originals)
        for tr in self.restituted:
            tr.network = tr.network[3:] 
         

    def load_resps(self):
        """
        NOT YET TESTED
        """
        print 'not ready!'
        loaded_resps = self.input_directory()
        for fn in glob.glob(loaded_resps):
            try:
                fn = fn.rsplit('/', 1)[1]
                print fn
                nslc = fn.split('.')[:4]
                print nslc
                self.resp_files[(nslc)] = fn
                print nslc
            except:
                raise


    def save_resps(self):
        print 'not yet....'

def __snufflings__():    
   return [ RestituteIrisData() ]

