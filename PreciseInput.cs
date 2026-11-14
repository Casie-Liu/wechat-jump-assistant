// Local timing worker. Contains no screen access, networking or game internals.
using System;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Threading;

class PreciseInput {
    [StructLayout(LayoutKind.Sequential)] struct MouseInput {
        public int dx, dy; public uint data, flags, time; public UIntPtr extra;
    }
    [StructLayout(LayoutKind.Sequential)] struct Input {
        public uint type; public MouseInput mouse;
    }
    [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint n, Input[] input, int size);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    [DllImport("winmm.dll")] static extern uint timeBeginPeriod(uint period);
    [DllImport("winmm.dll")] static extern uint timeEndPeriod(uint period);
    static readonly long Frequency=Stopwatch.Frequency;
    static bool Cancelled(IntPtr window) {
        return window!=IntPtr.Zero && (GetForegroundWindow()!=window ||
            (GetAsyncKeyState(0x1B)&0x8000)!=0 || (GetAsyncKeyState(0x77)&0x8000)!=0);
    }
    static bool WaitUntil(long deadline, IntPtr window) {
        long nextCheck=0;
        while (true) {
            long now=Stopwatch.GetTimestamp();
            if (now>=deadline) return false;
            if (now>=nextCheck) {
                if (Cancelled(window)) return true;
                nextCheck=now+Frequency/1000;
            }
            if (deadline-now>Frequency/100) Thread.Sleep(1);
            else Thread.SpinWait(12);
        }
    }
    static double Millis(long ticks) {return ticks*1000.0/Frequency;}
    static void Main(string[] args) {
        CultureInfo.CurrentCulture=CultureInfo.InvariantCulture;
        timeBeginPeriod(1);
        try {
            if (args.Length==1 && args[0]=="--bench") {
                double[] errors=new double[100];
                Thread worker=new Thread(delegate(){for(int i=0;i<100000000;i++) Math.Sqrt(i);});
                worker.IsBackground=true; worker.Start();
                Thread.CurrentThread.Priority=ThreadPriority.Highest;
                for(int i=0;i<errors.Length;i++) {
                    int ms=25+i%20; long start=Stopwatch.GetTimestamp();
                    WaitUntil(start+(long)(ms*Frequency/1000.0), IntPtr.Zero);
                    errors[i]=Millis(Stopwatch.GetTimestamp()-start)-ms;
                }
                Array.Sort(errors);
                Console.WriteLine("size={0} median={1:F4} p99={2:F4} max={3:F4}",Marshal.SizeOf(typeof(Input)),errors[50],errors[98],errors[99]);
                return;
            }
            if(args.Length!=1) return;
            IntPtr window=new IntPtr(long.Parse(args[0]));
            var down=new Input[]{new Input{mouse=new MouseInput{flags=2}}};
            var up=new Input[]{new Input{mouse=new MouseInput{flags=4}}};
            int size=Marshal.SizeOf(typeof(Input));
            // Warm up the managed timer before any real input.
            WaitUntil(Stopwatch.GetTimestamp()+Frequency/100,IntPtr.Zero);
            Console.WriteLine("READY "+size); Console.Out.Flush();
            string line;
            while((line=Console.ReadLine())!=null) {
                int ms;
                if(!int.TryParse(line,out ms) || ms<100 || ms>1600) break;
                if(Cancelled(window)) {Console.WriteLine("CANCELLED");Console.Out.Flush();continue;}
                long start=0, origin=0, release=0, ended=0; bool pressed=false, cancelled=false;
                try {
                    Thread.CurrentThread.Priority=ThreadPriority.Highest;
                    start=Stopwatch.GetTimestamp();
                    if(SendInput(1,down,size)!=1) throw new Exception("Mouse down rejected");
                    pressed=true; origin=Stopwatch.GetTimestamp();
                    cancelled=WaitUntil(origin+(long)(ms*Frequency/1000.0),window);
                } finally {
                    release=Stopwatch.GetTimestamp();
                    if(pressed && SendInput(1,up,size)!=1) Environment.Exit(2);
                    ended=Stopwatch.GetTimestamp();
                    Thread.CurrentThread.Priority=ThreadPriority.Normal;
                }
                Console.WriteLine("{0:R} {1:R} {2:R} {3}",Millis(release-origin),Millis(origin-start),Millis(ended-release),cancelled?1:0);
                Console.Out.Flush();
            }
        } finally {timeEndPeriod(1);}
    }
}
