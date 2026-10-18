// Native application window and its exclusively owned local worker.
#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#import <signal.h>

@interface Manager : NSObject <NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler>
@property NSWindow *window;
@property WKWebView *web;
@property NSTask *worker;
@property NSFileHandle *log;
@property NSMutableData *pending;
@property NSURL *origin;
@property NSString *token;
@property BOOL closing;
@property BOOL dirty;
@property BOOL busy;
@property BOOL checkingClose;
@property BOOL alignmentOwnsFullscreen;
@property BOOL wantsAlignmentFullscreen;
@property BOOL fullscreenTransition;
@end

@implementation Manager
- (void)message:(NSString *)title detail:(NSString *)detail {
    NSAlert *alert = [NSAlert new];
    alert.messageText = title;
    alert.informativeText = detail;
    [alert runModal];
}
- (void)fail:(NSString *)detail {
    [self message:@"KiCad Library Manager could not start" detail:detail];
    self.closing = YES;
    [NSApp terminate:nil];
}
- (void)menus {
    NSMenu *bar = [NSMenu new];
    NSMenuItem *appItem = [NSMenuItem new];
    [bar addItem:appItem];
    NSMenu *appMenu = [NSMenu new];
    [appMenu addItemWithTitle:@"About KiCad Library Manager" action:@selector(orderFrontStandardAboutPanel:) keyEquivalent:@""];
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:@"Quit KiCad Library Manager" action:@selector(terminate:) keyEquivalent:@"q"];
    appItem.submenu = appMenu;
    NSMenuItem *fileItem = [NSMenuItem new];
    [bar addItem:fileItem];
    NSMenu *file = [[NSMenu alloc] initWithTitle:@"File"];
    NSMenuItem *open = [file addItemWithTitle:@"Open Library…" action:@selector(openLibrary:) keyEquivalent:@"o"];
    open.target = self;
    [file addItemWithTitle:@"Close Window" action:@selector(performClose:) keyEquivalent:@"w"];
    fileItem.submenu = file;
    NSMenuItem *editItem = [NSMenuItem new];
    [bar addItem:editItem];
    NSMenu *edit = [[NSMenu alloc] initWithTitle:@"Edit"];
    [edit addItemWithTitle:@"Undo" action:@selector(undo:) keyEquivalent:@"z"];
    [edit addItemWithTitle:@"Redo" action:@selector(redo:) keyEquivalent:@"Z"];
    [edit addItem:[NSMenuItem separatorItem]];
    [edit addItemWithTitle:@"Cut" action:@selector(cut:) keyEquivalent:@"x"];
    [edit addItemWithTitle:@"Copy" action:@selector(copy:) keyEquivalent:@"c"];
    [edit addItemWithTitle:@"Paste" action:@selector(paste:) keyEquivalent:@"v"];
    [edit addItemWithTitle:@"Select All" action:@selector(selectAll:) keyEquivalent:@"a"];
    [edit addItem:[NSMenuItem separatorItem]];
    NSMenuItem *find = [edit addItemWithTitle:@"Find Components…" action:@selector(findComponents:) keyEquivalent:@"f"];
    find.target = self;
    editItem.submenu = edit;
    NSMenuItem *windowItem = [NSMenuItem new];
    [bar addItem:windowItem];
    NSMenu *window = [[NSMenu alloc] initWithTitle:@"Window"];
    [window addItemWithTitle:@"Minimize" action:@selector(performMiniaturize:) keyEquivalent:@"m"];
    [window addItemWithTitle:@"Zoom" action:@selector(performZoom:) keyEquivalent:@""];
    windowItem.submenu = window;
    NSApp.mainMenu = bar;
    NSApp.windowsMenu = window;
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [self menus];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1280, 850)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"KiCad Library Manager";
    self.window.minSize = NSMakeSize(900, 600);
    self.window.delegate = self;
    self.window.releasedWhenClosed = NO;
    [self.window setFrameAutosaveName:@"ManagerWindow"];
    [self.window center];
    WKWebViewConfiguration *config = [WKWebViewConfiguration new];
    config.websiteDataStore = WKWebsiteDataStore.nonPersistentDataStore;
    if (@available(macOS 12.3, *)) config.preferences.elementFullscreenEnabled = YES;
    [config.userContentController addScriptMessageHandler:self name:@"manager"];
    self.web = [[WKWebView alloc] initWithFrame:self.window.contentView.bounds configuration:config];
    self.web.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    self.web.navigationDelegate = self;
    self.web.UIDelegate = self;
    self.window.contentView = self.web;
    [self.web loadHTMLString:@"<html><body style='background:#f4f6ef;font:18px -apple-system;padding:50px;color:#526b3b'>Opening KiCad Library Manager…</body></html>" baseURL:nil];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];

    NSString *runtime = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"runtime"];
    NSString *entry = [runtime stringByAppendingPathComponent:@"app.py"];
    if (![[NSFileManager defaultManager] fileExistsAtPath:entry]) {
        [self fail:@"The application bundle is incomplete. Reinstall KiCad Library Manager."];
        return;
    }
    NSString *python = nil;
    for (NSString *candidate in @[@"/opt/homebrew/bin/python3", @"/usr/local/bin/python3", @"/usr/bin/python3"]) {
        if (![[NSFileManager defaultManager] isExecutableFileAtPath:candidate]) continue;
        NSTask *probe = [NSTask new];
        probe.executableURL = [NSURL fileURLWithPath:candidate];
        probe.arguments = @[@"-c", @"import sys; raise SystemExit(sys.version_info < (3,11))"];
        probe.standardOutput = NSFileHandle.fileHandleWithNullDevice;
        probe.standardError = NSFileHandle.fileHandleWithNullDevice;
        if ([probe launchAndReturnError:nil]) {
            [probe waitUntilExit];
            if (probe.terminationStatus == 0) { python = candidate; break; }
        }
    }
    if (!python) { [self fail:@"Install Python 3.11 or newer, then reopen the app."]; return; }
    NSString *logFolder = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Logs/KiCad Library Manager"];
    [[NSFileManager defaultManager] createDirectoryAtPath:logFolder withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *logPath = [logFolder stringByAppendingPathComponent:@"desktop.log"];
    if (![[NSFileManager defaultManager] fileExistsAtPath:logPath])
        [[NSFileManager defaultManager] createFileAtPath:logPath contents:nil attributes:@{NSFilePosixPermissions:@0600}];
    self.log = [NSFileHandle fileHandleForWritingAtPath:logPath];
    [self.log seekToEndOfFile];
    self.pending = [NSMutableData new];
    self.worker = [NSTask new];
    self.worker.executableURL = [NSURL fileURLWithPath:python];
    self.worker.arguments = @[@"-B", @"-u", entry, @"--desktop", @"--no-browser", @"--parent-pid", [NSString stringWithFormat:@"%d", getpid()]];
    self.worker.currentDirectoryURL = [NSURL fileURLWithPath:runtime];
    self.worker.standardInput = NSFileHandle.fileHandleWithNullDevice;
    NSPipe *pipe = [NSPipe pipe];
    self.worker.standardOutput = pipe;
    self.worker.standardError = pipe;
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(readOutput:) name:NSFileHandleReadCompletionNotification object:pipe.fileHandleForReading];
    [pipe.fileHandleForReading readInBackgroundAndNotify];
    __weak Manager *weakSelf = self;
    self.worker.terminationHandler = ^(NSTask *task) {
        dispatch_async(dispatch_get_main_queue(), ^{
            Manager *owner = weakSelf;
            if (!owner.closing && task.terminationStatus != 0)
                [owner message:@"The library worker stopped" detail:@"Reopen the app to continue. Details are in Library/Logs/KiCad Library Manager/desktop.log."];
            owner.closing = YES;
            [NSApp terminate:nil];
        });
    };
    NSError *error = nil;
    if (![self.worker launchAndReturnError:&error]) [self fail:error.localizedDescription];
}
- (void)readOutput:(NSNotification *)notification {
    NSData *data = notification.userInfo[NSFileHandleNotificationDataItem];
    if (!data.length) return;
    [self.log writeData:data];
    [self.pending appendData:data];
    NSData *newline = [@"\n" dataUsingEncoding:NSUTF8StringEncoding];
    NSRange range;
    while ((range = [self.pending rangeOfData:newline options:0 range:NSMakeRange(0,self.pending.length)]).location != NSNotFound) {
        NSString *line = [[NSString alloc] initWithData:[self.pending subdataWithRange:NSMakeRange(0,range.location)] encoding:NSUTF8StringEncoding];
        [self.pending replaceBytesInRange:NSMakeRange(0,range.location+1) withBytes:NULL length:0];
        if ([line hasPrefix:@"Library Manager: http://127.0.0.1:"]) {
            NSURL *url = [NSURL URLWithString:[line substringFromIndex:@"Library Manager: ".length]];
            NSURLComponents *parts = [NSURLComponents componentsWithURL:url resolvingAgainstBaseURL:NO];
            if (![parts.host isEqualToString:@"127.0.0.1"] || ![parts.fragment hasPrefix:@"token="]) continue;
            self.token = [parts.fragment substringFromIndex:6];
            parts.fragment = nil;
            self.origin = parts.URL;
            [self.web loadRequest:[NSURLRequest requestWithURL:url]];
        }
    }
    [notification.object readInBackgroundAndNotify];
}
- (BOOL)isLocal:(NSURL *)url {
    return self.origin && [url.scheme isEqualToString:self.origin.scheme] &&
        [url.host isEqualToString:self.origin.host] && [url.port isEqual:self.origin.port];
}
- (void)webView:(WKWebView *)web decidePolicyForNavigationAction:(WKNavigationAction *)action decisionHandler:(void (^)(WKNavigationActionPolicy))decision {
    NSURL *url = action.request.URL;
    if ([self isLocal:url] || (!self.origin && [url.scheme isEqualToString:@"about"])) {
        decision(WKNavigationActionPolicyAllow);
        return;
    }
    if (action.navigationType == WKNavigationTypeLinkActivated &&
        [@[@"https", @"http", @"mailto"] containsObject:url.scheme])
        [[NSWorkspace sharedWorkspace] openURL:url];
    decision(WKNavigationActionPolicyCancel);
}
- (WKWebView *)webView:(WKWebView *)web createWebViewWithConfiguration:(WKWebViewConfiguration *)configuration forNavigationAction:(WKNavigationAction *)action windowFeatures:(WKWindowFeatures *)features {
    NSURL *url = action.request.URL;
    if ([self isLocal:url]) [self.web loadRequest:action.request];
    else if ([@[@"https", @"http", @"mailto"] containsObject:url.scheme]) [[NSWorkspace sharedWorkspace] openURL:url];
    return nil;
}
- (void)webView:(WKWebView *)web runOpenPanelWithParameters:(WKOpenPanelParameters *)parameters initiatedByFrame:(WKFrameInfo *)frame completionHandler:(void (^)(NSArray<NSURL *> *))completion {
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.allowsMultipleSelection = parameters.allowsMultipleSelection;
    panel.canChooseDirectories = parameters.allowsDirectories;
    panel.canChooseFiles = !parameters.allowsDirectories;
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse result) {
        completion(result == NSModalResponseOK ? panel.URLs : nil);
    }];
}
- (void)webView:(WKWebView *)web runJavaScriptConfirmPanelWithMessage:(NSString *)message initiatedByFrame:(WKFrameInfo *)frame completionHandler:(void (^)(BOOL))completion {
    NSAlert *alert = [NSAlert new];
    alert.messageText = message;
    [alert addButtonWithTitle:@"Continue"];
    [alert addButtonWithTitle:@"Cancel"];
    completion([alert runModal] == NSAlertFirstButtonReturn);
}
- (void)webView:(WKWebView *)web runJavaScriptAlertPanelWithMessage:(NSString *)message initiatedByFrame:(WKFrameInfo *)frame completionHandler:(void (^)(void))completion {
    [self message:message detail:@""];
    completion();
}
- (void)reply:(NSString *)identifier value:(id)value {
    if (![identifier isKindOfClass:NSString.class]) return;
    NSData *json = [NSJSONSerialization dataWithJSONObject:@{@"id":identifier,@"value":value ?: NSNull.null} options:NSJSONWritingFragmentsAllowed error:nil];
    NSString *script = [NSString stringWithFormat:@"window.managerNativeResponse(%@)",[[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding]];
    [self.web evaluateJavaScript:script completionHandler:nil];
}
- (void)webView:(WKWebView *)web runJavaScriptTextInputPanelWithPrompt:(NSString *)prompt defaultText:(NSString *)defaultText initiatedByFrame:(WKFrameInfo *)frame completionHandler:(void (^)(NSString *))completion {
    NSAlert *alert = [NSAlert new];
    alert.messageText = prompt;
    NSTextField *field = [[NSTextField alloc] initWithFrame:NSMakeRect(0,0,360,24)];
    field.stringValue = defaultText ?: @"";
    alert.accessoryView = field;
    [alert addButtonWithTitle:@"Create"];
    [alert addButtonWithTitle:@"Cancel"];
    [alert.window setInitialFirstResponder:field];
    completion([alert runModal] == NSAlertFirstButtonReturn ? field.stringValue : nil);
}
- (void)userContentController:(WKUserContentController *)controller didReceiveScriptMessage:(WKScriptMessage *)message {
    if (![self isLocal:message.frameInfo.request.URL] || !message.frameInfo.mainFrame || ![message.body isKindOfClass:NSDictionary.class]) return;
    if ([message.body[@"type"] isEqual:@"choose-library"]) {
        NSOpenPanel *panel = [NSOpenPanel openPanel];
        panel.canChooseDirectories = YES;
        panel.canChooseFiles = NO;
        panel.canCreateDirectories = YES;
        panel.prompt = @"Choose Folder";
        [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse result) {
            [self reply:message.body[@"id"] value:result == NSModalResponseOK ? panel.URL.path : @""];
        }];
    } else if ([message.body[@"type"] isEqual:@"read-clipboard"]) {
        [self reply:message.body[@"id"] value:[NSPasteboard.generalPasteboard stringForType:NSPasteboardTypeString] ?: @""];
    } else if ([message.body[@"type"] isEqual:@"write-clipboard"] && [message.body[@"value"] isKindOfClass:NSString.class]) {
        [NSPasteboard.generalPasteboard clearContents];
        [NSPasteboard.generalPasteboard setString:message.body[@"value"] forType:NSPasteboardTypeString];
        [self reply:message.body[@"id"] value:nil];
    } else if ([message.body[@"type"] isEqual:@"state"]) {
        self.dirty = [message.body[@"dirty"] boolValue];
        self.busy = [message.body[@"busy"] boolValue];
    } else if ([message.body[@"type"] isEqual:@"quit"]) [self requestClose];
    else if ([message.body[@"type"] isEqual:@"alignment-fullscreen"]) {
        self.wantsAlignmentFullscreen = [message.body[@"enabled"] boolValue];
        BOOL full = (self.window.styleMask & NSWindowStyleMaskFullScreen) != 0;
        if (self.wantsAlignmentFullscreen && !full && !self.fullscreenTransition) {
            self.alignmentOwnsFullscreen = YES;
            [self.window toggleFullScreen:nil];
        } else if (!self.wantsAlignmentFullscreen && self.alignmentOwnsFullscreen && full && !self.fullscreenTransition) {
            [self.window toggleFullScreen:nil];
        }
    }
}
- (void)windowWillEnterFullScreen:(NSNotification *)notification { self.fullscreenTransition = YES; }
- (void)windowWillExitFullScreen:(NSNotification *)notification { self.fullscreenTransition = YES; }
- (void)windowDidEnterFullScreen:(NSNotification *)notification {
    self.fullscreenTransition = NO;
    if (self.alignmentOwnsFullscreen && !self.wantsAlignmentFullscreen)
        dispatch_async(dispatch_get_main_queue(), ^{ [self.window toggleFullScreen:nil]; });
}
- (void)windowDidExitFullScreen:(NSNotification *)notification {
    self.fullscreenTransition = NO;
    self.wantsAlignmentFullscreen = NO;
    self.alignmentOwnsFullscreen = NO;
    [self.web evaluateJavaScript:@"window.dispatchEvent(new Event('manager-exit-fullscreen'))" completionHandler:nil];
}
- (void)findComponents:(id)sender {
    [self.web evaluateJavaScript:@"window.dispatchEvent(new Event('manager-find'))" completionHandler:nil];
}
- (void)openLibrary:(id)sender {
    if (self.dirty || self.busy) {
        [self message:@"Finish editing first" detail:@"Save or cancel the open editor before switching libraries."];
        return;
    }
    [self.web evaluateJavaScript:@"window.dispatchEvent(new Event('manager-open-library'))" completionHandler:nil];
}
- (void)requestClose {
    if (self.closing || self.checkingClose) return;
    self.checkingClose = YES;
    [self.web evaluateJavaScript:@"window.managerCloseState ? window.managerCloseState() : null" completionHandler:^(id result, NSError *error) {
        self.checkingClose = NO;
        BOOL dirty = self.dirty, busy = self.busy;
        if ([result isKindOfClass:NSDictionary.class]) {
            dirty = [result[@"dirty"] boolValue];
            busy = [result[@"busy"] boolValue];
        }
        if (busy) {
            [self message:@"Please wait for the current operation" detail:@"The app will stay open so the operation can finish safely. Close it again afterward."];
            return;
        }
        if (dirty && ![self confirmDiscard]) return;
        [self stopWorker];
    }];
}
- (BOOL)confirmDiscard {
    NSAlert *alert = [NSAlert new];
    alert.messageText = @"Close without saving?";
    alert.informativeText = @"The open component editor may contain unsaved changes.";
    [alert addButtonWithTitle:@"Keep Editing"];
    [alert addButtonWithTitle:@"Discard and Close"];
    return [alert runModal] == NSAlertSecondButtonReturn;
}
- (void)stopWorker {
    if (!self.worker.running) { self.closing = YES; [NSApp terminate:nil]; return; }
    if (!self.origin) {
        // No requests can exist before the server publishes its listening URL.
        self.closing = YES;
        [self.worker terminate];
        return;
    }
    self.closing = YES;
    self.window.title = @"Closing KiCad Library Manager…";
    [self.web evaluateJavaScript:@"document.body.inert = true" completionHandler:nil];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:@"api/quit" relativeToURL:self.origin]];
    request.HTTPMethod = @"POST";
    request.HTTPBody = [@"{}" dataUsingEncoding:NSUTF8StringEncoding];
    [request setValue:self.token forHTTPHeaderField:@"X-Library-Token"];
    [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
    [[[NSURLSession sharedSession] dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        if (error && self.worker.running) dispatch_async(dispatch_get_main_queue(), ^{
            self.closing = NO;
            [self.web evaluateJavaScript:@"document.body.inert = false" completionHandler:nil];
            self.window.title = @"KiCad Library Manager";
            [self message:@"Could not close the app yet" detail:@"Wait for any operation to finish and try closing again."];
        });
    }] resume];
}
- (BOOL)windowShouldClose:(NSWindow *)sender { [self requestClose]; return NO; }
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    if (self.closing && !self.worker.running) return NSTerminateNow;
    [self requestClose];
    return NSTerminateCancel;
}
- (BOOL)applicationShouldHandleReopen:(NSApplication *)app hasVisibleWindows:(BOOL)visible {
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
    return YES;
}
- (void)applicationWillTerminate:(NSNotification *)notification {
    [self.log closeFile];
}
@end

#ifndef MANAGER_TESTING
int main(void) {
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        Manager *manager = [Manager new];
        app.delegate = manager;
        [app run];
    }
    return 0;
}
#endif
