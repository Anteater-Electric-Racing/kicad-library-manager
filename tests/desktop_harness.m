// Run the actual AppKit/WebKit host against a temporary library and real built UI.
#define MANAGER_TESTING 1
#import "../manager/macos/desktop.m"

@interface Harness : Manager
@property NSInteger phase;
@property NSInteger ticks;
@property BOOL discardPrompt;
@property BOOL busyPrompt;
@property BOOL allowDiscard;
@property BOOL failed;
@property NSTimer *timer;
@property NSMutableArray *checks;
@end
@implementation Harness
- (void)record:(NSString *)value { [self.checks addObject:value]; NSLog(@"CHECK: %@", value); }
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.checks = [NSMutableArray new];
    [super applicationDidFinishLaunching:notification];
    self.timer = [NSTimer scheduledTimerWithTimeInterval:0.3 target:self selector:@selector(tick:) userInfo:nil repeats:YES];
}
- (void)userContentController:(WKUserContentController *)controller didReceiveScriptMessage:(WKScriptMessage *)message {
    if ([message.body[@"type"] isEqual:@"alignment-fullscreen"]) NSLog(@"FULLSCREEN MESSAGE %@ local=%d main=%d",message.frameInfo.request.URL,[self isLocal:message.frameInfo.request.URL],message.frameInfo.mainFrame);
    [super userContentController:controller didReceiveScriptMessage:message];
}
- (BOOL)confirmDiscard { self.discardPrompt = YES; return self.allowDiscard; }
- (void)message:(NSString *)title detail:(NSString *)detail {
    if ([title isEqual:@"Please wait for the current operation"]) { self.busyPrompt = YES; return; }
    self.failed = YES;
    NSLog(@"UNEXPECTED ALERT: %@ %@",title,detail);
}
- (void)tick:(NSTimer *)timer {
    if (++self.ticks > 220 || self.failed) {
        self.failed = YES;
        [self.timer invalidate];
        self.allowDiscard = YES;
        [self stopWorker];
        return;
    }
    [self.web evaluateJavaScript:@"({text:document.body.innerText, state:window.managerCloseState?.(), canvas:!!document.querySelector('canvas')})" completionHandler:^(id result,NSError *error) {
        if (![result isKindOfClass:NSDictionary.class]) return;
        NSString *text = result[@"text"];

        if (self.phase == 0 && [text containsString:@"Desktop Fixture"] && [text containsString:@"Add component"]) {
            [self record:@"native window loaded remembered data-only library"];
            self.phase = 10;
            [self findComponents:nil];
        } else if (self.phase == 10) {
            self.phase = 11;
            [self.web evaluateJavaScript:@"document.activeElement?.getAttribute('aria-label') === 'Search components'" completionHandler:^(id focused, NSError *error) {
                if (error || ![focused boolValue]) { self.failed = YES; return; }
                [self record:@"native Find Components focuses catalog search"];
                [self.web evaluateJavaScript:@"document.activeElement.blur(); window.dispatchEvent(new KeyboardEvent('keydown',{key:'f',metaKey:true,bubbles:true,cancelable:true}))" completionHandler:nil];
            }];
        } else if (self.phase == 11) {
            self.phase = 12;
            [self.web evaluateJavaScript:@"document.activeElement?.getAttribute('aria-label') === 'Search components'" completionHandler:^(id focused, NSError *error) {
                if (error || ![focused boolValue]) { self.failed = YES; return; }
                [self record:@"Command-F focuses catalog search"];
                self.phase = 1;
                [self.web evaluateJavaScript:@"Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Add component').click()" completionHandler:nil];
            }];
        } else if (self.phase == 1 && [text containsString:@"Models that belong together"] && ![result[@"state"][@"busy"] boolValue]) {
            if (![result[@"state"][@"dirty"] boolValue]) { self.failed=YES; return; }
            [self record:@"editor publishes unsaved state"];
            self.phase = 20;
            [self.web evaluateJavaScript:@"Array.from(document.querySelectorAll('.type-grid button')).find(b=>b.textContent.trim()==='IC').click()" completionHandler:nil];
        } else if (self.phase == 20 && [text containsString:@"Standard package"]) {
            self.phase = 21;
            [self.web evaluateJavaScript:@"(()=>{const s=document.querySelector('[aria-label=\"Standard package\"]'); if(s.options.length!==7)throw Error('Expected six packages'); s.value='SOT-23';s.dispatchEvent(new Event('change',{bubbles:true}));})()" completionHandler:^(id value,NSError *error) { if(error)self.failed=YES; }];
        } else if (self.phase == 21 && ![result[@"state"][@"busy"] boolValue]) {
            self.phase = 23;
            [self.web evaluateJavaScript:@"Array.from(document.querySelectorAll('select')).filter(s=>s.selectedOptions[0]?.textContent.includes('SOT-23')).length>=3" completionHandler:^(id value,NSError *error) {
                if(error || ![value boolValue]){self.failed=YES;return;}
                [self record:@"IC dropdown loads SOT-23 footprint and STEP"];
                [self.web evaluateJavaScript:@"(()=>{const s=document.querySelector('[aria-label=\"Standard package\"]');s.value='TO-220-3_Horizontal_TabDown';s.dispatchEvent(new Event('change',{bubbles:true}));})()" completionHandler:^(id value,NSError *error){self.phase=22;}];
            }];
        } else if (self.phase == 22 && ![result[@"state"][@"busy"] boolValue]) {
            self.phase = 23;
            [self.web evaluateJavaScript:@"Array.from(document.querySelectorAll('select')).filter(s=>s.selectedOptions[0]?.textContent.includes('TO-220')).length>=3" completionHandler:^(id value,NSError *error) {
                if(error || ![value boolValue]){self.failed=YES;return;}
                [self record:@"IC dropdown switches to TO-220 tab-down footprint and STEP"];
                self.phase=2;
                [self requestClose];
            }];
        } else if (self.phase == 2 && self.discardPrompt && self.worker.running && !self.checkingClose) {
            [self record:@"Keep Editing prevents close"];
            self.phase = 3;
            [self.web evaluateJavaScript:@"window.originalCloseState=window.managerCloseState; window.managerCloseState=()=>({dirty:true,busy:true})" completionHandler:^(id value,NSError *error) { [self requestClose]; }];
        } else if (self.phase == 3 && self.busyPrompt && !self.checkingClose) {
            [self record:@"active operation prevents close"];
            self.phase = 4;
            [self.web evaluateJavaScript:@"window.managerCloseState=window.originalCloseState; Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='3D alignment').click()" completionHandler:nil];
        } else if (self.phase == 4 && [result[@"canvas"] boolValue] && [text containsString:@"PCB opacity"] && ![text containsString:@"Loading STEP"] && ![text containsString:@"unavailable"]) {
            [self record:@"WKWebView WebGL and STEP worker render; PCB slider visible"];
            self.phase = 5;
            [self.web evaluateJavaScript:@"Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Full screen').click()" completionHandler:nil];
        } else if (self.phase == 5 && [text.lowercaseString containsString:@"exit full screen"] && (self.window.styleMask & NSWindowStyleMaskFullScreen)) {
            [self record:@"native WebKit alignment fullscreen works"];
            self.phase = 6;
            [self.web evaluateJavaScript:@"document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))" completionHandler:nil];
        } else if (self.phase == 6 && !(self.window.styleMask & NSWindowStyleMaskFullScreen) && ![text.lowercaseString containsString:@"exit full screen"] && ![result[@"state"][@"busy"] boolValue]) {
            [self record:@"Escape exits alignment fullscreen"];
            self.phase = 7;
            self.allowDiscard = YES;
            [self.window performClose:nil];
        }
    }];
}
- (void)applicationWillTerminate:(NSNotification *)notification {
    [self.timer invalidate];
    NSDictionary *result = @{@"passed":@(!self.failed && self.phase==7 && !self.worker.running),@"phase":@(self.phase),@"checks":self.checks ?: @[],@"workerPID":@(self.worker.processIdentifier)};
    NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
    [data writeToFile:NSProcessInfo.processInfo.environment[@"MANAGER_TEST_RESULT"] atomically:YES];
    [super applicationWillTerminate:notification];
}
@end
int main(void) {
    @autoreleasepool {
        NSApplication *app=NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        Harness *harness=[Harness new];
        app.delegate=harness;
        [app run];
    }
    return 0;
}
