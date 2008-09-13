'''
Experimental GTK front-end for Shoebot

implements the gobject-based socket server from
http://roscidus.com/desktop/node/413
'''

import sys, gtk, random, StringIO
import shoebot
import cairo
import gobject, socket
from pprint import pprint

class ShoebotCanvas(gtk.DrawingArea):
    def __init__(self, mainwindow, box = None):
        super(ShoebotCanvas, self).__init__()
        self.connect("expose_event", self.expose)
        # get the box object to display
        self.box = box

        # make a dummy surface and context, otherwise scripts without draw()
        # and/or setup() will bork badly
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1,1)
        self.box.setsurface(target=surface)
        self.box.run()

        # set the window size to the one specified in the script
        self.set_size_request(self.box.WIDTH, self.box.HEIGHT)

    def expose(self, widget, event):
        '''Handle GTK expose events.'''

        # reset context
        self.context = None
        self.context = widget.window.cairo_create()
        # set a clip region for the expose event
        self.context.rectangle(event.area.x, event.area.y,
                            event.area.width, event.area.height)
        self.context.clip()

        # attach box to context
        self.box.setsurface(target=self.context)
        if 'setup' in self.box.namespace:
            self.box.namespace['setup']()
        if 'draw' in self.box.namespace:
            self.draw()

        # no setup() or draw() means we have to run the script on each step
        # FIXME: This actually makes static scripts run twice, not good.
        if not 'setup' in self.box.namespace and not 'draw' in self.box.namespace:
            self.box.run()

##        self.draw()
        return False

    def redraw(self,dummy='moo'):
        '''Handle redraws.'''
        # dummy is in the arguments because GTK seems to require it, but works
        # fine with any value, so we get away with this hack
        self.queue_draw()

    def draw(self):
        if 'draw' in self.box.namespace:
            self.box.namespace['draw']()

# additional functions for MainWindow
class SocketServerMixin:
    def server(self, host, port):
        '''Initialize server and start listening.'''
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(1)
        print "Listening on port %i..." % (port)
        gobject.io_add_watch(self.sock, gobject.IO_IN, self.listener)

    def listener(self, sock, *args):
        '''Asynchronous connection listener. Starts a handler for each connection.'''
        self.conn, self.addr = self.sock.accept()
        print "Connected"
        gobject.io_add_watch(self.conn, gobject.IO_IN, self.handler)
        return True

    def handler(self, conn, *args):
        '''Asynchronous connection handler. Processes each line from the socket.'''
        line = self.conn.recv(4096)
        if not len(line):
            print "Connection closed."
            return False
        else:
            incoming = line.strip()
            if len(incoming.split()) == 2:
                var, value = incoming.split()
                # is value in our variables list?
                if var in self.canvas.box.namespace:
                    # set the box namespace to the new value

                    ## TODO: we're forced to convert input to floats
                    # self.canvas.box.namespace[var] = value.strip(';')
                    self.canvas.box.namespace[var] = float(value.strip(';'))
                    # and redraw
                    self.canvas.redraw()
                return True
            else:
                return True

NUMBER = 1
TEXT = 2
BOOLEAN = 3
BUTTON = 4

class VarWindow:
    def __init__(self, parent, box):
        self.parent = parent

        window = gtk.Window()
        window.connect("destroy", self.do_quit)
        vbox = gtk.VBox(homogeneous=True, spacing=20)

        # set up sliders
        self.variables = []

        for item in box.vars:
            self.variables.append(item)
            if item.type is NUMBER:
                self.add_number(vbox, item)
            elif item.type is TEXT:
                self.add_text(vbox, item)
            elif item.type is BOOLEAN:
                self.add_boolean(vbox, item)
            elif item.type is BUTTON:
                self.add_button(vbox, item)

        window.add(vbox)
        window.set_size_request(400,35*len(self.variables))
        window.show_all()
        gtk.main()

    def add_number(self, container, v):
        # create a slider for each var
        sliderbox = gtk.HBox(homogeneous=False, spacing=0)
        label = gtk.Label(v.name)
        sliderbox.pack_start(label, False, True, 20)

        adj = gtk.Adjustment(v.value, v.min, v.max, .1, 2, 1)
        adj.connect("value_changed", self.cb_set_var, v)
        hscale = gtk.HScale(adj)
        hscale.set_value_pos(gtk.POS_RIGHT)
        sliderbox.pack_start(hscale, True, True, 0)
        container.pack_start(sliderbox, True, True, 0)

    def add_text(self, container, v):
        textcontainer = gtk.HBox(homogeneous=False, spacing=0)
        label = gtk.Label(v.name)
        textcontainer.pack_start(label, False, True, 20)

        entry = gtk.Entry(max=0)
        entry.set_text(v.value)
        entry.connect("changed", self.cb_set_var, v)
        textcontainer.pack_start(entry, True, True, 0)
        container.pack_start(textcontainer, True, True, 0)

    def add_boolean(self, v):
        pass

    def add_button(self, container, v):
        buttoncontainer = gtk.HBox(homogeneous=False, spacing=0)
        # in buttons, the varname is the function, so we use __name__
        button = gtk.Button(label=v.name.__name__)
        button.connect("clicked", self.parent.box.namespace[v.name], None)
        buttoncontainer.pack_start(button, True, True, 0)
        container.pack_start(buttoncontainer, True, True, 0)


    def do_quit(self, widget):
        gtk.main_quit()

    def cb_set_var(self, widget, v):
        ''' Called when a slider is adjusted. '''
        # set the appropriate canvas var
        if v.type is NUMBER:
            self.parent.canvas.box.namespace[v.name] = widget.value
        elif v.type is TEXT:
            self.parent.canvas.box.namespace[v.name] = widget.get_text()
        # and redraw the canvas
        self.parent.canvas.redraw()

class ShoebotWindow(SocketServerMixin):
    def __init__(self, code=None, server=False, serverport=7777, varwindow=False):
        self.box = shoebot.Box(gtkmode=True, inputscript=code)
        self.canvas = ShoebotCanvas(self, self.box)
        self.has_server = server
        self.serverport = serverport
        self.has_varwindow = varwindow

    def run(self):
        '''Setup the main GTK window.'''
        window = gtk.Window()
        window.connect("destroy", self.do_quit)
        window.add(self.canvas)
        if self.has_server:
            self.server('', self.serverport)
        window.show_all()

        if self.has_varwindow:
            VarWindow(self, self.box)

        gtk.main()

    def do_quit(self, widget):
        if self.has_server:
            self.sock.close()
        gtk.main_quit()


##if __name__ == "__main__":
##    import sys
##    win = MainWindow('letter_h_obj.py')
##    win.server('',7777)
##    win.run()