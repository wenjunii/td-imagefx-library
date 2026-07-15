uniform float uMix; uniform float uFeed; uniform float uKill; uniform float uDiffusion; uniform float uSeed;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec2 px = 1.0 / vec2(textureSize(sTD2DInputs[1], 0)); vec4 src = texture(sTD2DInputs[0], uv);
    vec2 c = texture(sTD2DInputs[1], uv).rg; vec2 lap = -c;
    lap += .2 * (texture(sTD2DInputs[1], uv + vec2(px.x,0)).rg + texture(sTD2DInputs[1], uv - vec2(px.x,0)).rg + texture(sTD2DInputs[1], uv + vec2(0,px.y)).rg + texture(sTD2DInputs[1], uv - vec2(0,px.y)).rg);
    lap += .05 * (texture(sTD2DInputs[1], uv + px).rg + texture(sTD2DInputs[1], uv - px).rg + texture(sTD2DInputs[1], uv + vec2(px.x,-px.y)).rg + texture(sTD2DInputs[1], uv + vec2(-px.x,px.y)).rg);
    float a = max(c.r, .001), b = max(c.g, dot(src.rgb, vec3(.3333)) * uSeed); float reaction = a*b*b;
    vec2 nextState = clamp(vec2(a + (lap.r*uDiffusion - reaction + uFeed*(1.0-a)), b + (lap.g*uDiffusion*.5 + reaction - (uKill+uFeed)*b)), 0.0, 1.0);
    vec3 color = vec3(nextState.r - nextState.g, nextState.g, 1.0 - nextState.r);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, color, clamp(uMix, 0.0, 1.0)), src.a));
}
