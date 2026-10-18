import AppKit
let image = NSImage(size:NSSize(width:1024,height:1024))
image.lockFocus()
NSColor(calibratedRed:0.20,green:0.32,blue:0.24,alpha:1).setFill()
NSBezierPath(roundedRect:NSRect(x:56,y:56,width:912,height:912),xRadius:204,yRadius:204).fill()
NSColor(calibratedRed:0.30,green:0.46,blue:0.34,alpha:1).setStroke()
let inner=NSBezierPath(roundedRect:NSRect(x:96,y:96,width:832,height:832),xRadius:170,yRadius:170)
inner.lineWidth=8;inner.stroke()
let gold=NSColor(calibratedRed:0.83,green:0.69,blue:0.37,alpha:1)
for y in [310,512,714] {
    gold.setStroke()
    let trace=NSBezierPath();trace.move(to:NSPoint(x:170,y:y));trace.line(to:NSPoint(x:300,y:y));trace.lineWidth=22;trace.stroke()
    gold.setFill();NSBezierPath(ovalIn:NSRect(x:140,y:y-30,width:60,height:60)).fill()
}
NSColor(calibratedRed:0.93,green:0.95,blue:0.86,alpha:1).setStroke()
let k=NSBezierPath();k.move(to:NSPoint(x:388,y:282));k.line(to:NSPoint(x:388,y:742));k.move(to:NSPoint(x:700,y:742));k.line(to:NSPoint(x:412,y:497));k.line(to:NSPoint(x:724,y:282));k.lineWidth=64;k.lineCapStyle = .round;k.lineJoinStyle = .round;k.stroke()
gold.setFill();NSBezierPath(ovalIn:NSRect(x:770,y:480,width:64,height:64)).fill()
image.unlockFocus()
let bitmap=NSBitmapImageRep(data:image.tiffRepresentation!)!
try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:CommandLine.arguments[1]))
